"""
Run stage3 (HeyGen) for every stage4 lesson that already has slide_*.png + script.json.

Writes lesson_heygen.mp4 in each m##_v## folder (avatar + slide backgrounds). Stage1 output.mp4
has no avatar — that is expected; use this script after batch_stage1.py.

  python batch_stage3.py
  python batch_stage3.py --dry-run
  python batch_stage3.py --from-lesson m02_v01
  python batch_stage3.py --from-lesson m01_v01 --to-lesson m03_v02   # only completed so far; pipeline w/ batch_stage1
  python batch_stage3.py --from-lesson m01_v02   # resume: skips existing lesson_heygen.mp4 unless you add --force

Requires: stage3/.env (HEYGEN_API_KEY, optional HEYGEN_AVATAR_ID/VOICE_ID, optional HEYGEN_POLL_TIMEOUT_MINUTES=120+).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_LESSON_RE = re.compile(r"^m(\d{2})_v(\d{2})$")


def _discover_lesson_dirs(out_root: Path) -> list[Path]:
    found: list[tuple[int, int, Path]] = []
    if not out_root.is_dir():
        return []
    for d in sorted(out_root.iterdir()):
        if not d.is_dir():
            continue
        m = _LESSON_RE.match(d.name)
        if not m:
            continue
        if not (d / "script.json").is_file():
            continue
        if not any(d.glob("slide_*.png")):
            continue
        found.append((int(m.group(1)), int(m.group(2)), d))
    found.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in found]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch stage3 HeyGen for all stage4 lessons (avatar + slides)"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List lessons only; do not call HeyGen",
    )
    p.add_argument(
        "--from-lesson",
        metavar="M##_V##",
        help="Only run this lesson and later (e.g. m02_v01).",
    )
    p.add_argument(
        "--to-lesson",
        metavar="M##_V##",
        help="Only run up to and including this lesson (e.g. m03_v02; use while other lessons are still in batch_stage1).",
    )
    p.add_argument(
        "--out-root",
        type=Path,
        help="Override stage4 output root (default: stage4/output/)",
    )
    p.add_argument(
        "--out-name",
        default="lesson_heygen.mp4",
        help="Filename inside each lesson folder (default: lesson_heygen.mp4)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-render even if lesson_heygen.mp4 already exists (default: skip existing files)",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    here = Path(__file__).resolve().parent
    out_root = (args.out_root or (here / "output")).resolve()
    stage3_run = (here.parent / "stage3" / "run_stage3.py").resolve()
    if not stage3_run.is_file():
        raise SystemExit(f"Not found: {stage3_run}")

    lessons = _discover_lesson_dirs(out_root)
    if not lessons:
        raise SystemExit(
            f"No lesson folders with script.json + slide_*.png under {out_root}. "
            "Run batch_stage1.py first."
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
        for d in lessons:
            pm = _LESSON_RE.match(d.name)
            assert pm
            m, v = int(pm.group(1)), int(pm.group(2))
            if (m, v) < (m0, v0):
                continue
            filtered.append(d)
        lessons = filtered
        if not lessons:
            raise SystemExit("No lessons left after --from-lesson filter.")

    if args.to_lesson:
        tl = args.to_lesson.strip().lower()
        tm = _LESSON_RE.match(tl)
        if not tm:
            raise SystemExit(
                f"--to-lesson must look like m03_v02, got: {args.to_lesson!r}"
            )
        m1, v1 = int(tm.group(1)), int(tm.group(2))
        filtered2: list[Path] = []
        for d in lessons:
            pm = _LESSON_RE.match(d.name)
            assert pm
            m, v = int(pm.group(1)), int(pm.group(2))
            if (m, v) > (m1, v1):
                continue
            filtered2.append(d)
        lessons = filtered2
        if not lessons:
            raise SystemExit("No lessons left after --to-lesson filter.")

    n = len(lessons)
    for i, lesson in enumerate(lessons, start=1):
        rel = lesson.relative_to(out_root)
        out_mp4 = lesson / args.out_name
        script = lesson / "script.json"
        if (
            not args.force
            and not args.dry_run
            and out_mp4.is_file()
            and out_mp4.stat().st_size > 0
        ):
            print(f"\n{'='*60}\n[{i}/{n}] {rel} -> SKIP (already exists: {out_mp4.name})\n{'='*60}")
            continue
        print(f"\n{'='*60}\n[{i}/{n}] {rel} -> {out_mp4.name}\n{'='*60}")
        if args.dry_run:
            print("  (dry-run) would run run_stage3.py --skip-stage1 ...")
            continue
        r = subprocess.run(
            [
                sys.executable,
                str(stage3_run),
                "--script",
                str(script),
                "--slides-dir",
                str(lesson.resolve()),
                "--skip-stage1",
                "--out",
                str(out_mp4.resolve()),
            ],
            cwd=str(stage3_run.parent),
        )
        if r.returncode != 0:
            raise SystemExit(
                f"run_stage3 failed (exit {r.returncode}) for {rel}. "
                "Re-run with: python batch_stage3.py --from-lesson {rel} "
                "(skips finished videos). If timeout: set HEYGEN_POLL_TIMEOUT_MINUTES=180 in stage3/.env."
            )

    if args.dry_run:
        print(f"\nDry-run: {n} lesson(s) would be processed.")
    else:
        print(
            f"\nDone. {n} avatar video(s). Open * / {args.out_name} in each lesson folder."
        )


if __name__ == "__main__":
    main()
