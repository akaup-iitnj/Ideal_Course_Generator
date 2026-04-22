"""
Generate Udemy "Course landing page" and related upload details (text + course image).

Follows the same field groupings as a typical upload flow:
  - Course title, subtitle, description (200+ words), what is primarily taught
  - Basic info hints: language, level, category / subcategory
  - Course image: Udemy 750x422, jpg/png/gif, no text on the image (enforced in image prompt)
  - Promotional video: we only output talking points / script outline (not a rendered video)

Course image: generated with the Images API (default model gpt-image-2; DALL·E 3 as fallback), then
resized to exactly 750x422 for upload.

Env (optional):
  OPENAI_LANDING_TEXT_MODEL  (default: gpt-4o)
  OPENAI_LANDING_IMAGE_MODEL (default: gpt-image-2; fallback: dall-e-3)
"""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Any

# Udemy (from Course Upload Details.pdf and common limits)
UDEMY_COURSE_TITLE_MAX = 60
UDEMY_COURSE_SUBTITLE_MAX = 120
UDEMY_COURSE_IMAGE_W = 750
UDEMY_COURSE_IMAGE_H = 422
MIN_DESCRIPTION_WORDS = 200

# 16:9 landscape for API (resize to 750x422); edges multiple of 16
GPT_IMAGE2_LANDSCAPE = "2048x1152"


def _text_model() -> str:
    return (os.environ.get("OPENAI_LANDING_TEXT_MODEL") or "gpt-4o").strip()


def _image_model() -> str:
    return (os.environ.get("OPENAI_LANDING_IMAGE_MODEL") or "gpt-image-2").strip()


def _prompt_for_nontext_hero(image_prompt: str) -> str:
    base = (image_prompt or "").strip()
    rules = (
        " The image must contain NO text, NO letters, NO numbers, NO logos, "
        "NO watermarks, NO UI, NO captions — only the visual scene. "
        "Style: clean, professional, suitable for an online course thumbnail."
    )
    return base + rules


def generate_landing_page_json(
    client: Any,
    source_text: str,
    outline: dict[str, Any],
    *,
    max_source_chars: int = 100_000,
) -> dict[str, Any]:
    st = (source_text or "")[:max_source_chars]
    outline_blob = json.dumps(
        {k: outline.get(k) for k in ("course_title", "total_course_minutes", "modules", "source_pdf")
         if k in outline},
        ensure_ascii=False,
        indent=2,
    )
    system = f"""You write marketing copy for a Udemy course landing page. Output ONE JSON object only
(no markdown, no code fences) with this exact structure:
{{
  "course_title": "<string, max {UDEMY_COURSE_TITLE_MAX} characters; attention-grabbing, informative, search-friendly>",
  "course_subtitle": "<string, max {UDEMY_COURSE_SUBTITLE_MAX} chars. Use 1-2 strong keywords; mention 3-4 of the most important areas covered.>",
  "what_is_primarily_taught": "<2-4 sentences: what is primarily taught in the course; plain text.>",
  "course_description": "<plain text, minimum {MIN_DESCRIPTION_WORDS} words; multiple short paragraphs; compelling; describe outcomes and who the course is for. No HTML required unless you think simple <p> helps — plain paragraphs are OK. Use \\n\\n between paragraphs.>",
  "language": "English (US)",
  "suggested_level": "<one of: Beginner | Intermediate | Advanced | All Levels; pick the best match>",
  "suggested_category": "<broad e.g. Business, or Development>",
  "suggested_subcategory": "<Udemy subcategory that fits, or closest guess>",
  "promo_video_talking_points": [
    "<45-90 second talking-head outline: bullet 1>",
    "bullet 2",
    "..."
  ],
  "course_image_prompt": "<A single visual scene description in English for an image model: subject, setting, mood, color palette, lighting. No request for text in the image — we will enforce no text separately.>"
}}
Rules:
- Base content on the course outline and the source text themes; be accurate, not generic fluff.
- course_description must be at least {MIN_DESCRIPTION_WORDS} words.
- Subtitle and title must fit the character maxima (shorter is fine).
- Return only valid JSON."""

    user = f"""Course outline (authoritative structure):
{outline_blob}

--- SOURCE EXCERPT (for themes and facts) ---

{st}"""

    r = client.chat.completions.create(
        model=_text_model(),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = (r.choices[0].message.content or "").strip()
    if not raw:
        raise RuntimeError("Empty model response (landing page JSON)")
    return json.loads(raw)


def _decode_image_result(result: Any) -> bytes:
    if not result.data:
        raise RuntimeError("Image API returned no data")
    item = result.data[0]
    b64 = getattr(item, "b64_json", None)
    if b64:
        return base64.b64decode(b64)
    u = getattr(item, "url", None)
    if u:
        import httpx

        with httpx.Client(timeout=120.0) as h:
            return h.get(str(u)).content
    raise RuntimeError("Image response has neither b64_json nor url")


def _generate_image_bytes(client: Any, prompt: str) -> tuple[bytes, str]:
    """
    Returns (raw_image_bytes, model_used). Tries gpt-image-2 (or env model), then dall-e-3.
    """
    primary = _image_model()
    last_err: str | None = None
    order: list[str] = []
    for m in (primary, "dall-e-3"):
        if m not in order:
            order.append(m)
    for model in order:
        try:
            if model == "dall-e-3":
                result = client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    n=1,
                    size="1792x1024",
                    response_format="b64_json",
                )
            else:
                result = client.images.generate(
                    model=model,
                    prompt=prompt,
                    n=1,
                    size=GPT_IMAGE2_LANDSCAPE,
                    quality="low",
                )
            return _decode_image_result(result), model
        except Exception as e:  # noqa: BLE001
            last_err = f"{model}: {e}"
            continue
    raise RuntimeError(f"Image generation failed: {last_err}")


def _resize_to_udemy_course_image(raw: bytes) -> bytes:
    from PIL import Image  # type: ignore

    im = Image.open(io.BytesIO(raw))
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    im = im.resize(
        (UDEMY_COURSE_IMAGE_W, UDEMY_COURSE_IMAGE_H),
        Image.Resampling.LANCZOS,
    )
    buf = io.BytesIO()
    im.save(
        buf,
        format="JPEG",
        quality=90,
        optimize=True,
    )
    return buf.getvalue()


def write_landing_artifacts(
    client: Any,
    source_text: str,
    outline: dict[str, Any],
    landing_dir: Path,
    *,
    with_images: bool = True,
) -> dict[str, Any]:
    """
    Writes:
      landing_dir/course_landing.json
      landing_dir/course_image_udemy.jpg  (if with_images; 750x422; jpeg)

    Returns the landing dict (including generated_files, full_image_prompt_used when applicable).
    """
    landing_dir = landing_dir.resolve()
    landing_dir.mkdir(parents=True, exist_ok=True)

    data = generate_landing_page_json(client, source_text, outline)
    data["udemy_image_requirements"] = {
        "width": UDEMY_COURSE_IMAGE_W,
        "height": UDEMY_COURSE_IMAGE_H,
        "formats": ["jpg", "jpeg", "png", "gif"],
        "udemy_rule": "No text on the course image (per Udemy quality standards).",
    }

    gen_files: dict[str, str] = {}
    full_prompt = ""

    if with_images:
        pvisual = (data.get("course_image_prompt") or "").strip()
        if not pvisual:
            pvisual = f"Visual metaphor for: {outline.get('course_title', 'online course')}"
        full_prompt = _prompt_for_nontext_hero(pvisual)
        try:
            raw, model_used = _generate_image_bytes(client, full_prompt)
            jpg = _resize_to_udemy_course_image(raw)
            jpg_path = landing_dir / "course_image_udemy.jpg"
            jpg_path.write_bytes(jpg)
            gen_files["course_image_udemy"] = "landing/course_image_udemy.jpg"
            data["course_image_model"] = model_used
            data["full_image_prompt_used"] = full_prompt
        except Exception as e:  # noqa: BLE001
            data["course_image_error"] = str(e)
            data["full_image_prompt_intended"] = full_prompt
    else:
        data["course_image_skipped"] = (
            "Re-run with --no-landing-images omitted to generate 750x422 image (gpt-image-2 or DALL·E 3 fallback)."
        )

    data["generated_files"] = gen_files

    (landing_dir / "course_landing.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return data
