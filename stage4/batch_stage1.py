"""
Run stage1 make_video for every stage4 lesson: output/m##_v##/script.json

Writes slides, TTS, and output.mp4 into each lesson folder (same directory as script.json).

  python batch_stage1.py
  python batch_stage1.py --dry-run
  python batch_stage1.py --from-lesson m01_v02   # skip earlier lessons (resume)
  python batch_stage1.py --force   # same as without; overwrites every lesson

Requires: same as stage1 (LibreOffice, ffmpeg, stage1/.env with OPENAI_API_KEY).
For an on-screen avatar, run `python batch_stage3.py` after (HeyGen; see stage3/.env).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_LESSON_RE = re.compile(r"^m(\d{2})_v(\d{2})$")


def _discover_script_paths(out_root: Path) -> list[Path]:
    found: list[tuple[int, int, Path]] = []
    if not out_root.is_dir():
        return []
    for d in sorted(out_root.iterdir()):
        if not d.is_dir():
            continue
        m = _LESSON_RE.match(d.name)
        if not m:
            continue
        sc = d / "script.json"
        if not sc.is_file():
            continue
        found.append((int(m.group(1)), int(m.group(2)), sc))
    found.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in found]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch stage1 --from-json for all stage4 output/m##_v##/script.json"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List lessons only; do not run make_video",
    )
    p.add_argument(
        "--from-lesson",
        metavar="M##_V##",
        help="Only run this lesson and later (e.g. m01_v02). Default: from m01_v01 (all).",
    )
    p.add_argument(
        "--out-root",
        type=Path,
        help="Override stage4 output root (default: stage4/output/)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Optional. Stage1 always overwrites each lesson; this flag exists for shell compatibility only.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    here = Path(__file__).resolve().parent
    out_root = (args.out_root or (here / "output")).resolve()
    make_video = (here.parent / "stage1" / "make_video.py").resolve()
    if not make_video.is_file():
        raise SystemExit(f"Not found: {make_video}")

    all_scripts = _discover_script_paths(out_root)
    if not all_scripts:
        raise SystemExit(
            f"No m##_v##/script.json under {out_root}. Run: python run_stage4.py --all-scripts"
        )

    if args.from_lesson:
        fl = args.from_lesson.strip().lower()
        fm = _LESSON_RE.match(fl)
        if not fm:
            raise SystemExit(
                f"--from-lesson must look like m01_v02, got: {args.from_lesson!r}"
            )
        m0, v0 = int(fm.group(1)), int(fm.group(2))
        filtered: list[Path] = []
        for p in all_scripts:
            pm = _LESSON_RE.match(p.parent.name)
            assert pm
            m, v = int(pm.group(1)), int(pm.group(2))
            if (m, v) < (m0, v0):
                continue
            filtered.append(p)
        all_scripts = filtered
        if not all_scripts:
            raise SystemExit("No lessons left after --from-lesson filter.")

    n = len(all_scripts)
    for i, script_path in enumerate(all_scripts, start=1):
        lesson = script_path.parent
        rel = script_path.parent.relative_to(out_root)
        print(f"\n{'='*60}\n[{i}/{n}] {rel}\n{'='*60}")
        if args.dry_run:
            print("  (dry-run) would run make_video --from-json ->", script_path)
            continue
        r = subprocess.run(
            [
                sys.executable,
                str(make_video),
                "--from-json",
                str(script_path),
                "--out",
                str(lesson),
            ],
            check=False,
        )
        if r.returncode != 0:
            raise SystemExit(
                f"make_video failed (exit {r.returncode}) for {script_path}. "
                "Fix the issue, then re-run with --from-lesson for this key."
            )

    if args.dry_run:
        print(f"\nDry-run: {n} lesson(s) would be processed.")
    else:
        print(f"\nDone. {n} lesson(s). MP4 in each: <lesson>/output.mp4 under {out_root}")


if __name__ == "__main__":
    main()
