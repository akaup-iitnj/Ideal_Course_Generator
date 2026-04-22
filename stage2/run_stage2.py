"""
Stage 2: folder of PDFs -> output/extracted/ (per-PDF text + images) + output/script.json
Same slide contract as stage1. Progress via print() only.

  python run_stage2.py "Lesson title"        # full: extract + GPT -> output/script.json
  python run_stage2.py --extract-only        # PyMuPDF only
  python run_stage2.py --script-only "Title"  # from existing output/extracted/

OpenAI: stage2/.env or stage1/.env (UTF-8, no BOM).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Cap source text used for outline (rough token budget; adjust if you hit model limits)
MAX_SOURCE_CHARS: int = 100_000


def _base_dirs() -> tuple[Path, Path]:
    here = Path(__file__).resolve().parent
    return here, here / "output" / "extracted"


# --- Slice 1: text per page ---------------------------------------------------


def _extract_images_for_page(
    doc: "Any", page: "Any", page_index: int, img_dir: Path, doc_label: str
) -> int:
    count = 0
    for idx, im in enumerate(page.get_images(), start=1):
        xref = im[0]
        try:
            sm = doc.extract_image(xref)
        except (RuntimeError, ValueError) as e:
            print(
                f"  [{doc_label}] p{page_index + 1} skip image: {e}",
            )
            continue
        ext = (sm.get("ext") or "png").lower() if sm.get("ext") else "png"
        if ext not in ("png", "jpeg", "jpg", "jp2", "jpx", "gif", "bmp", "tiff"):
            ext = "png"
        out_name = f"p{page_index + 1:03d}_i{idx:02d}.{ext}"
        (img_dir / out_name).write_bytes(sm["image"])
        count += 1
    return count


def extract_one_pdf(pdf: Path, extracted_root: Path) -> None:
    """Create extracted_root/<pdf_stem>/ with text/ and images/; fitz = PyMuPDF (same as stage1)."""
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


def _safe_stem(pdf: Path) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", pdf.stem)
    return s[:180] or "document"


# --- Slice 2: already merged into extract_one_pdf (images) --------------------


# --- Slice 3: build prompt text + GPT -> script.json -------------------------


def _openai_client():
    from dotenv import load_dotenv
    from openai import OpenAI

    here = Path(__file__).resolve().parent
    stage1_env = here.parent / "stage1" / ".env"
    if (here / ".env").is_file():
        load_dotenv(here / ".env")
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    # Empty OPENAI_API_KEY= in stage2/.env would block; fall back to stage1.
    if not key and stage1_env.is_file():
        load_dotenv(stage1_env, override=True)
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit(
            "Missing OPENAI_API_KEY. For --script-only / full run, set it in stage2/.env "
            "or in stage1/.env (same file is loaded as fallback; UTF-8, no BOM)."
        )
    return OpenAI(api_key=key)


def _collect_source_text(extracted_root: Path) -> str:
    """Concatenate all page_*.txt from every PDF subfolder, stable sort."""
    parts: list[str] = []
    for sub in sorted(p for p in extracted_root.iterdir() if p.is_dir()):
        text_dir = sub / "text"
        if not text_dir.is_dir():
            continue
        txts = sorted(text_dir.glob("page_*.txt"))
        for tf in txts:
            body = tf.read_text(encoding="utf-8", errors="replace").strip()
            if not body:
                continue
            rel = f"{sub.name}/{tf.name}"
            parts.append(f"=== {rel} ===\n{body}\n")
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


def generate_script_from_extracted(source_text: str, topic: str) -> dict[str, Any]:
    """
    One GPT-4o call, JSON object mode, same slide schema as stage1. source_text = PDF(s) text only.
    """
    client = _openai_client()
    if len(source_text) > MAX_SOURCE_CHARS:
        print(
            f"  Warning: truncating source from {len(source_text)} to {MAX_SOURCE_CHARS} characters."
        )
        source_text = source_text[:MAX_SOURCE_CHARS]

    system = """You turn raw PDF extract into a short video lesson. Output ONE JSON object only (no markdown, no code fences) with this exact shape:
{
  "topic": "<must equal the user lesson title exactly>",
  "slides": [
    {
      "slide_num": 1,
      "title": "<string>",
      "bullets": ["<string>", "..."],
      "narration": "<2-4 sentences, conversational; what the presenter says>"
    }
  ]
}
Rules: 6 to 8 slides. Each slide: 1 title, 2-4 short bullets, one narration. slide_num 1..N. Bullets and narration must reflect the source text where possible; if the extract is weak, do your best and stay on-topic. Narration is spoken only. Return only valid JSON."""

    user = f"Lesson title (use verbatim for 'topic' field): {topic}\n\n--- SOURCE TEXT FROM PDFs ---\n\n{source_text}"
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
        raise RuntimeError("Empty model response")
    data: dict[str, Any] = json.loads(raw)
    return _normalize_script(data, topic)


# --- Entrypoints -------------------------------------------------------------


def run_extract_only(input_dir: Path, extracted_root: Path) -> None:
    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(
            f"No .pdf files in {input_dir.resolve()}. Add PDFs and run again."
        )
    extracted_root.mkdir(parents=True, exist_ok=True)
    for p in pdfs:
        extract_one_pdf(p, extracted_root)
    print(f"Done (extract only). Data under {extracted_root.resolve()}")


def run_script_only(topic: str, extracted_root: Path, out_json: Path) -> None:
    if not extracted_root.is_dir() or not any(extracted_root.iterdir()):
        raise SystemExit(
            f"No extracted data in {extracted_root}. Run with --extract-only or full run first."
        )
    st = _collect_source_text(extracted_root)
    if not st:
        raise SystemExit("No text found under extracted/*/text/page_*.txt")
    print(f"Collected {len(st)} characters from extracts; calling GPT-4o...")
    script = generate_script_from_extracted(st, topic)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(script, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {out_json.resolve()}")


def run_full(topic: str, input_dir: Path, extracted_root: Path, out_json: Path) -> None:
    run_extract_only(input_dir, extracted_root)
    run_script_only(topic, extracted_root, out_json)
    print(f"\nAll steps done. Open {out_json} or feed it to stage1 for video later.")


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Stage 2: PDFs in input/ -> output/extracted/ + output/script.json"
    )
    p.add_argument(
        "topic",
        nargs="*",
        help='Lesson title (e.g. "Intro to MOSFETs"). Required for default and --script-only unless using --extract-only.',
    )
    p.add_argument(
        "--extract-only",
        action="store_true",
        help="Only run PyMuPDF extract (text + images), no API.",
    )
    p.add_argument(
        "--script-only",
        action="store_true",
        help="Build script.json from existing output/extracted/ (requires .env and topic).",
    )
    return p.parse_args()


if __name__ == "__main__":
    here, ex_root = _base_dirs()
    input_dir = here / "input"
    out_json = here / "output" / "script.json"
    args = _parse()
    input_dir.mkdir(parents=True, exist_ok=True)
    (here / "output").mkdir(parents=True, exist_ok=True)
    topic = " ".join(args.topic).strip() or "Lesson from source PDFs"

    if args.script_only and args.extract_only:
        print("Use only one of --script-only or --extract-only", file=sys.stderr)
        raise SystemExit(2)
    if args.extract_only:
        run_extract_only(input_dir, ex_root)
    elif args.script_only:
        run_script_only(topic, ex_root, out_json)
    else:
        run_full(topic, input_dir, ex_root, out_json)
