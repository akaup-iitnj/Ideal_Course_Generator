"""
Build a plain-text Udemy instructor uploader reference from course_outline.json.

Maps pipeline terminology to Udemy:
  - Our "module"  → Udemy "Section"
  - Our "video"   → Udemy "Lecture" (a curriculum item of type video)

Field limits (Udemy curriculum builder) — match what you type in the UI:
  - Section title: 80 characters
  - "What will students be able to do at the end of this section?": 200 characters
  - Lecture title: 80 characters
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

UDEMY_SECTION_TITLE_MAX = 80
UDEMY_SECTION_LEARNING_OBJECTIVE_MAX = 200
UDEMY_LECTURE_TITLE_MAX = 80
# Course landing (Udemy “Course landing page”)
UDEMY_COURSE_TITLE_MAX = 60
UDEMY_COURSE_SUBTITLE_MAX = 120

def load_landing_dict(out_root: Path) -> dict[str, Any] | None:
    """If present, stage4 output/landing/course_landing.json from a prior run."""
    p = (out_root / "landing" / "course_landing.json").resolve()
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _count_note(text: str, max_len: int) -> str:
    t = (text or "").strip()
    n = len(t)
    if n <= max_len:
        return f"{n} / {max_len} — OK for Udemy"
    return f"{n} / {max_len} — shorten by {n - max_len} character(s) before pasting in Udemy"


def _udemy_terminology_block() -> str:
    return """\
Udemy screen names (so labels match the instructor site)
----------------------------------------------------------------------
• Section  — a chapter that groups lessons (we call this a "module" in JSON).
• Lecture  — one curriculum item, usually your uploaded video.
• "Curriculum item" — the + control adds a new lecture, quiz, or assignment; use a video lecture for each row below.
• Learning objective — the prompt "What will students be able to do at the end of this section?" (per section, not per lecture).

"""


def _format_landing_uploader_block(
    landing: dict[str, Any], *, rel_base: str = "stage4/output"
) -> str:
    """
    Text for Udemy’s Course landing page (title, subtitle, description, what is taught, image, promo).
    `rel_base` is the folder that contains the `landing/` subfolder in printed paths.
    """
    lines: list[str] = []
    lines.append("COURSE LANDING PAGE (Udemy: publish → course / landing page & basics)")
    lines.append("=" * 70)
    lines.append(
        "Use these in the **Course landing page** and related upload screens (see Course Upload Details)."
    )
    lines.append("")

    ct = (landing.get("course_title") or "").strip()
    if ct:
        lines.append("Course title  (search-friendly, attention-grabbing; typical limit ~60 characters)")
        lines.append(f"  {ct}")
        lines.append(f"  {_count_note(ct, UDEMY_COURSE_TITLE_MAX)}")
        lines.append("")

    sub = (landing.get("course_subtitle") or "").strip()
    if sub:
        lines.append(
            "Course subtitle  (1–2 keywords; 3–4 areas you cover; typical limit ~120 characters)"
        )
        lines.append(f"  {sub}")
        lines.append(f"  {_count_note(sub, UDEMY_COURSE_SUBTITLE_MAX)}")
        lines.append("")

    wpt = (landing.get("what_is_primarily_taught") or landing.get("what_is_primarly_taught") or "").strip()
    if wpt:
        lines.append("What is primarily taught in your course?  (short field)")
        lines.append(f"  {wpt}")
        lines.append("")

    desc = (landing.get("course_description") or "").strip()
    if desc:
        lines.append("Course description  (Udemy: minimum 200 words — paste and trim if the box requires it)")
        for para in desc.split("\n\n"):
            for line in para.strip().splitlines():
                lines.append(f"  {line}")
            lines.append("")
        wc = len(desc.split())
        if wc < 200:
            lines.append(
                f"  [!] Word count about {wc}; target at least 200 words for Udemy — expand manually if needed."
            )
        else:
            lines.append(f"  (About {wc} words.)")
        lines.append("")

    lang = (landing.get("language") or "").strip()
    lev = (landing.get("suggested_level") or "").strip()
    cat = (landing.get("suggested_category") or "").strip()
    subc = (landing.get("suggested_subcategory") or "").strip()
    if any((lang, lev, cat, subc)):
        lines.append("Basic info  (suggestions — match your real category tree in Udemy)")
        if lang:
            lines.append(f"  Language: {lang}")
        if lev:
            lines.append(f"  Level: {lev}")
        if cat:
            lines.append(f"  Category: {cat}")
        if subc:
            lines.append(f"  Subcategory: {subc}")
        lines.append("")

    lines.append("Course image  (750×422 px, .jpg / .jpeg / .gif / .png; no text on the image, per Udemy)")
    gf = landing.get("generated_files") or {}
    relp = (gf.get("course_image_udemy") or "landing/course_image_udemy.jpg").strip(
        "/"
    )
    if relp:
        lines.append(f"  Generated file: {rel_base.rstrip('/')}/{relp}")
    if landing.get("course_image_error"):
        lines.append(f"  Image generation failed: {landing.get('course_image_error')}")
    lines.append("  If the file exists, upload it in the “Course image” / promotional thumbnail area.")
    lines.append("")

    promo = landing.get("promo_video_talking_points")
    lines.append("Promotional video  (we do not render a file — use as script / talking points for your recording)")
    if isinstance(promo, list) and promo:
        for i, b in enumerate(promo, start=1):
            t = (str(b) or "").strip()
            if t:
                lines.append(f"  {i}. {t}")
    else:
        lines.append("  (No bullets in course_landing.json — regenerate landing or add your own script.)")
    lines.append("")

    lines.append("Instructor profile(s)")
    lines.append("  — Fill in the Udemy instructor profile separately in your account; not generated here.")
    lines.append("")

    return "\n".join(lines)


def _learning_objective_for_section(module: dict[str, Any]) -> str:
    """Text for Udemy’s section field; prefer module summary, trimmed to limit with note in doc."""
    s = (module.get("summary") or "").strip()
    if not s:
        s = "Describe what students will be able to do after this section (use your own words, max 200 characters in Udemy)."
    return s


def build_uploader_text_from_outline(
    outline: dict[str, Any],
    *,
    stage4_output_rel: str = "stage4/output",
    include_heygen: bool = True,
    landing: dict[str, Any] | None = None,
) -> str:
    """
    Returns UTF-8 friendly plain text for uploader_reference.txt
    `stage4_output_rel` is how we refer to lesson folders in prose (no absolute paths).
    `landing` — optional `course_landing.json` object for the Course landing page block.
    """
    lines: list[str] = []
    course_title = (outline.get("course_title") or "Course").strip()
    source_pdf = (outline.get("source_pdf") or "").strip()
    total_min = outline.get("total_course_minutes", 60)

    lines.append("Udemy uploader reference")
    lines.append("=" * 70)
    lines.append("")
    lines.append("Use this file while filling the **Curriculum** and **Course landing page** in the Udemy")
    lines.append("instructor dashboard.")
    lines.append("")

    if landing:
        lines.append(_format_landing_uploader_block(landing, rel_base=stage4_output_rel))
        lines.append("—" * 35)
        lines.append("")

    lines.append("Use the lower sections while filling the **Curriculum** page: **Section** titles,")
    lines.append("**Learning objective** lines, and **Lecture** titles, then upload lesson videos from")
    lines.append("the folder paths under each lecture.")
    lines.append("")
    lines.append(_udemy_terminology_block().rstrip())
    lines.append("Course outline (source)")
    lines.append("-" * 70)
    lines.append(f"Working title: {course_title}")
    if source_pdf:
        lines.append(f"Source PDF: {source_pdf}")
    lines.append(
        f"Planned run time (from outline): about {total_min} minutes (all sections)."
    )
    lines.append("")

    modules = outline.get("modules")
    if not isinstance(modules, list):
        modules = []

    for m in modules:
        if not isinstance(m, dict):
            continue
        mod_num = int(m.get("module_num", 0) or 0)
        sec_title = (m.get("title") or f"Section {mod_num}").strip()
        lo = _learning_objective_for_section(m)

        lines.append("")
        lines.append(f"Section {mod_num} (paste into 'New section' or edit existing)")
        lines.append("-" * 70)
        lines.append("Section title  (max 80 characters; counter on the right in Udemy)")
        lines.append(f"  {sec_title}")
        lines.append(f"  {_count_note(sec_title, UDEMY_SECTION_TITLE_MAX)}")
        lines.append("")
        lines.append(
            "What will students be able to do at the end of this section?  (max 200 characters)"
        )
        lines.append(f"  {lo}")
        lines.append(f"  {_count_note(lo, UDEMY_SECTION_LEARNING_OBJECTIVE_MAX)}")
        lines.append("")

        videos = m.get("videos")
        if not isinstance(videos, list):
            videos = []

        for v in videos:
            if not isinstance(v, dict):
                continue
            vn = int(v.get("video_num", 0) or 0)
            key = f"m{mod_num:02d}_v{vn:02d}"
            vtitle = (v.get("title") or f"Video {vn}").strip()
            focus = (v.get("learning_focus") or "").strip()
            lines.append(
                f"  Lecture {vn}  (curriculum item — add with '+ Curriculum item' → Video, or reorder after upload)"
            )
            lines.append("  ---")
            lines.append("  Lecture title  (max 80 characters)")
            lines.append(f"    {vtitle}")
            lines.append(
                f"    {_count_note(vtitle, UDEMY_LECTURE_TITLE_MAX)}"
            )
            if focus:
                lines.append("  For your own notes (not a separate Udemy field at lecture level):")
                lines.append(f"    Learning focus: {focus}")
            rel_dir = f"{stage4_output_rel}/{key}"
            lines.append("  After batch render, upload the primary video from:")
            lines.append(f"    {rel_dir}/output.mp4")
            if include_heygen:
                lines.append("  If you used HeyGen (batch stage3), prefer:")
                lines.append(f"    {rel_dir}/lesson_heygen.mp4")
            lines.append("")

    lines.append("End of uploader reference")
    lines.append("")
    return "\n".join(lines)


def build_single_lesson_uploader_text(
    lecture_title: str,
    *,
    section_title: str = "Main section",
    section_learning_objective: str = "",
    video_folder_rel: str = "stage1/output",
) -> str:
    """
    One video / one section — typical stage2 → stage1 run. Suggested text for a minimal Udemy
    course with a single section and one lecture.
    """
    lo = (section_learning_objective or "").strip()
    if not lo:
        lo = (
            f"After this section, students can apply the ideas from \"{lecture_title.strip()[:80]}\" "
            "in context. (Edit to one clear outcome, max 200 characters in Udemy.)"
        )
    st = (section_title or "Main section").strip()
    lt = (lecture_title or "Lecture 1").strip()
    lines: list[str] = []
    lines.append("Udemy uploader reference (single lesson / stage2 → stage1)")
    lines.append("=" * 70)
    lines.append("")
    lines.append(_udemy_terminology_block().rstrip())
    lines.append("One section, one video lecture: fill Section 1, then add one video curriculum item.")
    lines.append("")

    lines.append("Section 1")
    lines.append("-" * 70)
    lines.append("Section title  (max 80 characters)")
    lines.append(f"  {st}")
    lines.append(f"  {_count_note(st, UDEMY_SECTION_TITLE_MAX)}")
    lines.append("")
    lines.append(
        "What will students be able to do at the end of this section?  (max 200 characters)"
    )
    lines.append(f"  {lo}")
    lines.append(f"  {_count_note(lo, UDEMY_SECTION_LEARNING_OBJECTIVE_MAX)}")
    lines.append("")

    lines.append("Lecture 1  (add with '+ Curriculum item' → Video)")
    lines.append("-" * 70)
    lines.append("Lecture title  (max 80 characters)")
    lines.append(f"  {lt}")
    lines.append(f"  {_count_note(lt, UDEMY_LECTURE_TITLE_MAX)}")
    lines.append("")
    lines.append("After stage1, upload the rendered video from:")
    lines.append(f"  {video_folder_rel.rstrip('/')}/output.mp4")
    lines.append("If you use HeyGen (stage3) from that folder, upload instead:")
    lines.append(f"  {video_folder_rel.rstrip('/')}/lesson_heygen.mp4")
    lines.append("")
    lines.append("End of uploader reference")
    lines.append("")
    return "\n".join(lines)


def _load_outline(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    here = Path(__file__).resolve().parent
    default_json = here / "output" / "course_outline.json"
    p = argparse.ArgumentParser(
        description="Regenerate uploader_reference.txt from course_outline.json (no API)."
    )
    p.add_argument(
        "--outline",
        type=Path,
        help="Path to course_outline.json (default: stage4/output/course_outline.json)",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Output path (default: same folder as outline, uploader_reference.txt)",
    )
    p.add_argument(
        "--prefix",
        default="stage4/output",
        help="Path prefix to print for m##_v## folders (default: stage4/output)",
    )
    p.add_argument(
        "--no-heygen",
        action="store_true",
        help="Omit lesson_heygen.mp4 lines",
    )
    args = p.parse_args()
    jp: Path
    if args.outline is not None:
        jp = Path(args.outline)
    else:
        jp = default_json
    if not jp.is_file():
        raise SystemExit(f"Not found: {jp}")

    outline = _load_outline(jp)
    landing = load_landing_dict(jp.parent)
    text = build_uploader_text_from_outline(
        outline,
        stage4_output_rel=args.prefix,
        include_heygen=not args.no_heygen,
        landing=landing,
    )
    if args.out is not None:
        out_p = Path(args.out)
    else:
        out_p = jp.parent / "uploader_reference.txt"
    out_p.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {out_p.resolve()}")


if __name__ == "__main__":
    main()
