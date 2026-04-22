"""
Stage 4: one PDF (Kimball / specialty food) -> course outline (5 modules x 4 videos) + optional
per-video script.json for stage1 (6–8 slides, ~3 min spoken per video).

  python run_stage4.py
      # default: first PDF in input/ -> output/extracted/ + output/course_outline.json
  python run_stage4.py --pdf "C:\path\book.pdf"
  python run_stage4.py --extract-only
  python run_stage4.py --all-scripts
      # after outline, writes output/m##_v##/script.json (20 files; many API calls)

  python batch_stage1.py
      # for each m##_v##/script.json, runs stage1; writes output.mp4 in that lesson folder

OpenAI: stage4/.env or stage1/.env (UTF-8, no BOM), same as stage2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Match stage2: cap for one prompt
MAX_SOURCE_CHARS: int = 100_000


def _base_dirs() -> tuple[Path, Path, Path]:
    here = Path(__file__).resolve().parent
    return here, here / "output" / "extracted", here / "output"


def _openai_client():
    from dotenv import load_dotenv
    from openai import OpenAI

    here = Path(__file__).resolve().parent
    stage1_env = here.parent / "stage1" / ".env"
    if (here / ".env").is_file():
        load_dotenv(here / ".env")
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key and stage1_env.is_file():
        load_dotenv(stage1_env, override=True)
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit(
            "Missing OPENAI_API_KEY. Set in stage4/.env or stage1/.env (UTF-8, no BOM)."
        )
    return OpenAI(api_key=key)


def _safe_stem(pdf: Path) -> str:
    """
    Windows-safe folder name under 120 chars. PDFs with long 'libgen.li' names can exceed
    MAX_PATH when nested under output/extracted/.
    """
    s = re.sub(r'[<>:"/\\|?*\[\]]', "_", pdf.stem)
    s = re.sub(r"[\s_]+", "_", s).strip("._")
    s = s[:100] or "document"
    h = hashlib.md5(pdf.name.encode("utf-8", errors="replace")).hexdigest()[:8]
    return f"{s}_{h}"


def _extract_images_for_page(
    doc: Any, page: Any, page_index: int, img_dir: Path, doc_label: str
) -> int:
    count = 0
    for idx, im in enumerate(page.get_images(), start=1):
        xref = im[0]
        try:
            sm = doc.extract_image(xref)
        except (RuntimeError, ValueError) as e:
            print(f"  [{doc_label}] p{page_index + 1} skip image: {e}")
            continue
        ext = (sm.get("ext") or "png").lower() if sm.get("ext") else "png"
        if ext not in ("png", "jpeg", "jpg", "jp2", "jpx", "gif", "bmp", "tiff"):
            ext = "png"
        out_name = f"p{page_index + 1:03d}_i{idx:02d}.{ext}"
        (img_dir / out_name).write_bytes(sm["image"])
        count += 1
    return count


def extract_one_pdf(pdf: Path, extracted_root: Path) -> None:
    import fitz  # type: ignore[import-not-found]

    stem = _safe_stem(pdf)
    out = extracted_root / stem
    text_dir = out / "text"
    img_dir = out / "images"
    text_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting: {pdf.name} -> {out.name}/")
    doc = fitz.open(pdf)
    total_imgs = 0
    n_pages = 0
    try:
        n_pages = len(doc)
        for pno in range(n_pages):
            page = doc[pno]
            t = (page.get_text("text") or "").strip()
            (text_dir / f"page_{pno + 1:03d}.txt").write_text(
                t, encoding="utf-8", newline="\n"
            )
            n = _extract_images_for_page(doc, page, pno, img_dir, stem)
            total_imgs += n
    finally:
        doc.close()

    meta = {"source": pdf.name, "pages": n_pages}
    (out / "meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"  {stem}: {meta['pages']} page(s), {total_imgs} image file(s) written")


def _collect_source_text_for_stem(extracted_root: Path, stem: str) -> str:
    sub = extracted_root / stem
    text_dir = sub / "text"
    if not text_dir.is_dir():
        return ""
    parts: list[str] = []
    for tf in sorted(text_dir.glob("page_*.txt")):
        body = tf.read_text(encoding="utf-8", errors="replace").strip()
        if not body:
            continue
        parts.append(f"=== {tf.name} ===\n{body}\n")
    return "\n".join(parts).strip()


def _normalize_script(data: dict[str, Any], topic: str) -> dict[str, Any]:
    if "topic" not in data or "slides" not in data:
        raise ValueError("Model output must have 'topic' and 'slides'")
    data["topic"] = topic
    for i, slide in enumerate(data["slides"], start=1):
        if not isinstance(slide, dict):
            raise TypeError(f"slides[{i-1}] must be a dict")
        for k in ("slide_num", "title", "bullets", "narration"):
            if k not in slide:
                raise ValueError(f"slide {i} missing '{k}'")
        slide["slide_num"] = i
        if not isinstance(slide["bullets"], list):
            raise TypeError(f"slide {i} bullets must be a list")
    return data


def generate_course_outline(
    source_text: str,
    course_title: str,
) -> dict[str, Any]:
    client = _openai_client()
    if len(source_text) > MAX_SOURCE_CHARS:
        print(
            f"  Warning: truncating source from {len(source_text)} to {MAX_SOURCE_CHARS} characters."
        )
        source_text = source_text[:MAX_SOURCE_CHARS]

    system = """You design a short online course from the supplied book text. Output ONE JSON object only (no markdown, no code fences) with this exact structure:
{
  "course_title": "<string, matches user course theme>",
  "total_course_minutes": 60,
  "modules": [
    {
      "module_num": 1,
      "title": "<module title>",
      "module_minutes": 12,
      "summary": "<2-3 sentences; what this module covers, grounded in the source>",
      "videos": [
        {
          "video_num": 1,
          "title": "<short video title>",
          "duration_minutes": 3,
          "learning_focus": "<1-2 sentences: what the learner takes away>"
        }
      ]
    }
  ]
}
Rules:
- Exactly 5 modules. module_num 1..5.
- Each module has exactly 4 videos. video_num 1..4 within that module.
- Each video duration_minutes must be 3; each module_minutes 12; total 60.
- Titles and learning_focus must follow themes from the book (regulations, product development, packaging, sales channels, food safety, business planning, etc. as the text allows).
- Order modules in a logical teaching sequence for someone starting a specialty food business.
- Return only valid JSON."""

    user = f"""Course theme (use in course_title): {course_title}

--- SOURCE TEXT (excerpt from book) ---

{source_text}"""

    r = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = (r.choices[0].message.content or "").strip()
    if not raw:
        raise RuntimeError("Empty model response (outline)")
    data: dict[str, Any] = json.loads(raw)
    return _validate_outline(data, course_title)


def _validate_outline(data: dict[str, Any], course_title: str) -> dict[str, Any]:
    if "modules" not in data:
        raise ValueError("outline missing 'modules'")
    modules = data["modules"]
    if not isinstance(modules, list) or len(modules) != 5:
        raise ValueError("outline must have exactly 5 modules")
    for i, m in enumerate(modules, start=1):
        if m.get("module_num") != i:
            m["module_num"] = i
        vids = m.get("videos")
        if not isinstance(vids, list) or len(vids) != 4:
            raise ValueError(f"module {i} must have exactly 4 videos")
        for j, v in enumerate(vids, start=1):
            if v.get("video_num") != j:
                v["video_num"] = j
            v["duration_minutes"] = 3
        m["module_minutes"] = 12
    data["course_title"] = data.get("course_title") or course_title
    data["total_course_minutes"] = 60
    return data


def generate_lesson_script(
    source_text: str,
    topic: str,
    outline_context: str,
) -> dict[str, Any]:
    client = _openai_client()
    if len(source_text) > MAX_SOURCE_CHARS:
        source_text = source_text[:MAX_SOURCE_CHARS]

    system = """You turn book/source text into one short video lesson script. Output ONE JSON object only (no markdown, no code fences) with this exact shape:
{
  "topic": "<must equal the user lesson title exactly>",
  "slides": [
    {
      "slide_num": 1,
      "title": "<string>",
      "bullets": ["<string>", "..."],
      "narration": "<spoken lines for this slide; conversational>"
    }
  ]
}
Rules:
- 6 to 8 slides. Together the narrations should support roughly 3 minutes of speech at a moderate teaching pace (slightly more detail per slide than a 2-minute lesson).
- Each slide: 1 title, 2-4 short bullets, one narration. No image fields (figures are added in a later step from the PDF extract).
- Ground content in the SOURCE TEXT; if something is not in the extract, only add generic, accurate business advice.
- slide_num 1..N. Return only valid JSON."""

    user = f"""Lesson title (use verbatim for 'topic' field): {topic}

Context from course outline (for alignment only):
{outline_context}

--- SOURCE TEXT FROM BOOK ---

{source_text}"""

    r = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = (r.choices[0].message.content or "").strip()
    if not raw:
        raise RuntimeError("Empty model response (lesson script)")
    data: dict[str, Any] = json.loads(raw)
    return _normalize_script(data, topic)


def _list_extracted_image_names(images_dir: Path) -> list[str]:
    """Filenames from PDF extract (pPAGE_index.ext), skip tiny files."""
    if not images_dir.is_dir():
        return []
    out: list[str] = []
    for f in sorted(images_dir.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".jp2", ".jpx"):
            continue
        try:
            if f.stat().st_size < 2048:
                continue
        except OSError:
            continue
        out.append(f.name)
    return out[:120]


def enrich_script_with_extracted_images(
    script: dict[str, Any], lesson_dir: Path, images_dir: Path
) -> dict[str, Any]:
    """
    Set source_images_dir and per-slide image (filename) using GPT + PDF /images only.
    """
    names = _list_extracted_image_names(images_dir)
    if not names:
        return script
    client = _openai_client()
    slides_in = [
        {
            "slide_num": s.get("slide_num"),
            "title": s.get("title"),
            "bullets": s.get("bullets"),
        }
        for s in script.get("slides", [])
    ]
    system = """You map slides to at most one figure from a textbook. Output ONE JSON only:
{ "assignments": { "1": "p012_i01.png" or null, "2": null, ... } }
Keys are slide numbers as strings. Use only filenames from the list (or null). Match topics to the figure; avoid decorative fluff."""
    user = "Slides:\n" + json.dumps(
        slides_in, ensure_ascii=False, indent=2
    ) + "\n\nAvailable image files (pPAGE_index in PDF order):\n" + "\n".join(names)
    r = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = (r.choices[0].message.content or "").strip()
    if not raw:
        return script
    data: dict[str, Any] = json.loads(raw)
    assign = data.get("assignments") or {}
    name_set = set(names)
    try:
        rel = os.path.relpath(
            str(images_dir.resolve()), str(lesson_dir.resolve())
        )
        script["source_images_dir"] = Path(rel).as_posix()
    except ValueError:
        script["source_images_dir"] = str(images_dir.resolve())
    for s in script.get("slides", []):
        if not isinstance(s, dict):
            continue
        try:
            sn = str(int(s.get("slide_num", 0)))
        except (TypeError, ValueError):
            continue
        fn = assign.get(sn)
        if fn in (None, ""):
            continue
        if not isinstance(fn, (str, int, float)):
            continue
        fn = str(fn).strip()
        if fn.lower() in ("null", "none"):
            continue
        if fn in name_set:
            s["image"] = fn
        else:
            print(f"  Warning: unknown image {fn!r} for slide {sn}, skipped")
    return script


def _flatten_lessons(outline: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for m in outline["modules"]:
        mn = m["module_num"]
        for v in m["videos"]:
            vn = v["video_num"]
            key = f"m{mn:02d}_v{vn:02d}"
            title = f"Module {mn}: {m['title']} — Video {vn}: {v['title']}"
            rows.append(
                {
                    "key": key,
                    "module_num": mn,
                    "video_num": vn,
                    "topic": title,
                    "video_title": v["title"],
                    "module_title": m["title"],
                    "focus": v.get("learning_focus", ""),
                }
            )
    return rows


def _outline_context_for_lesson(lesson: dict[str, Any], outline: dict[str, Any]) -> str:
    m = next(
        x for x in outline["modules"] if x["module_num"] == lesson["module_num"]
    )
    v = next(
        x for x in m["videos"] if x["video_num"] == lesson["video_num"]
    )
    return json.dumps(
        {
            "module": m.get("summary", ""),
            "video": v.get("learning_focus", ""),
        },
        ensure_ascii=False,
    )


def run_extract(pdf: Path, extracted_root: Path) -> str:
    extracted_root.mkdir(parents=True, exist_ok=True)
    extract_one_pdf(pdf, extracted_root)
    return _safe_stem(pdf)


def run_all_scripts(
    source_text: str, outline: dict[str, Any], out_root: Path, ex_root: Path
) -> None:
    stem = str(outline.get("extracted_stem") or "").strip()
    images_root = (ex_root / stem / "images") if stem else None
    lessons = _flatten_lessons(outline)
    total = len(lessons)
    for i, le in enumerate(lessons, start=1):
        ctx = _outline_context_for_lesson(le, outline)
        print(
            f"[{i}/{total}] Generating script: {le['key']} ...",
        )
        script = generate_lesson_script(source_text, le["topic"], ctx)
        d = out_root / le["key"]
        d.mkdir(parents=True, exist_ok=True)
        if images_root and images_root.is_dir():
            print(f"  Assigning PDF figures from {images_root.name} ...")
            script = enrich_script_with_extracted_images(script, d, images_root)
        p = d / "script.json"
        p.write_text(
            json.dumps(script, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"  Wrote {p}")


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Stage 4: PDF -> 5x4 course outline (+ optional 20x script.json)"
    )
    p.add_argument(
        "--pdf",
        type=Path,
        help="Path to .pdf. Default: first .pdf in stage4/input/",
    )
    p.add_argument(
        "--course-title",
        default="Start Your Own Food Business",
        help="Theme line for the outline (default: start-your-own food business).",
    )
    p.add_argument(
        "--extract-only",
        action="store_true",
        help="Only PyMuPDF extract to output/extracted/, no API.",
    )
    p.add_argument(
        "--all-scripts",
        action="store_true",
        help="After outline, generate 20x script.json (expensive).",
    )
    return p.parse_args()


if __name__ == "__main__":
    here, ex_root, out_root = _base_dirs()
    args = _parse()
    here.mkdir(parents=True, exist_ok=True)
    (here / "input").mkdir(parents=True, exist_ok=True)
    out_root.mkdir(parents=True, exist_ok=True)

    pdf: Path | None = args.pdf
    if not pdf:
        cand = sorted((here / "input").glob("*.pdf"))
        if not cand:
            raise SystemExit(
                f"No PDF. Place a .pdf in {here / 'input'} or pass --pdf \"C:\\\\path\\\\file.pdf\""
            )
        pdf = cand[0]
    else:
        pdf = pdf.resolve()
        if not pdf.is_file():
            raise SystemExit(f"Not a file: {pdf}")

    stem = run_extract(pdf, ex_root)
    if args.extract_only:
        print(f"Done (extract only). stem={stem}")
        raise SystemExit(0)

    source = _collect_source_text_for_stem(ex_root, stem)
    if not source:
        raise SystemExit("No text extracted; check PDF.")

    print(f"Collected {len(source)} characters; generating course outline (5 modules x 4 videos)...")
    outline = generate_course_outline(source, args.course_title)
    outline_path = out_root / "course_outline.json"
    outline["source_pdf"] = pdf.name
    outline["extracted_stem"] = stem
    outline_path.write_text(
        json.dumps(outline, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {outline_path.resolve()}")

    if args.all_scripts:
        print("Generating per-lesson script.json (20 API calls)...")
        run_all_scripts(source, outline, out_root, ex_root)
        print("Done. Render all local MP4s: python batch_stage1.py  (in this folder)")

    print(
        "\nNext: python batch_stage1.py  (slide+TTS -> output.mp4, no avatar). "
        "Then: python batch_stage3.py  (HeyGen -> lesson_heygen.mp4 with avatar in each folder)."
    )
