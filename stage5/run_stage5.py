"""
Stage 5 (CLI): full-course batch — thin wrapper around pipeline.py

  python run_stage5.py
  python run_stage5.py --from-stage1
  python run_stage5.py --heygen-only
  python run_stage5.py --no-heygen
  python run_stage5.py --course-title "..." --pdf "C:\\path\\book.pdf"

Web UI: see app.py  (uvicorn app:app --host 0.0.0.0 --port 8755)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline import PipelineError, run_pipeline, validate_options


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Stage 5: full-course batch (stage4 + batch_stage1 + batch_stage3)"
    )
    p.add_argument(
        "--from-stage1",
        action="store_true",
        help="Skip stage4; run batch_stage1 + batch_stage3 (scripts under stage4/output/).",
    )
    p.add_argument(
        "--heygen-only",
        action="store_true",
        help="Run only batch_stage3 (avatar MP4s).",
    )
    p.add_argument(
        "--no-heygen",
        action="store_true",
        help="Run stage4 + batch_stage1; skip batch_stage3.",
    )
    p.add_argument(
        "--course-title",
        default="Start Your Own Food Business",
        help="Passed to run_stage4.py (default: Start Your Own Food Business).",
    )
    p.add_argument(
        "--pdf",
        type=Path,
        help="Path to .pdf. Default: first PDF in stage4/input/.",
    )
    p.add_argument(
        "--force-heygen",
        action="store_true",
        help="Pass --force to batch_stage3 (re-render existing lesson_heygen.mp4).",
    )
    p.add_argument(
        "--force-stage1",
        action="store_true",
        help="Pass --force to batch_stage1 (compatibility; stage1 always overwrites).",
    )
    p.add_argument(
        "--num-modules",
        type=int,
        default=5,
        help="Number of course sections in the stage4 outline (default: 5).",
    )
    p.add_argument(
        "--duration-hours",
        type=int,
        default=1,
        help="Target course hours for outline sizing (default: 1).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse()
    try:
        validate_options(
            args.from_stage1, args.heygen_only, args.no_heygen
        )
    except ValueError as e:
        print(e, file=sys.stderr)
        raise SystemExit(2) from e
    project_root = Path(__file__).resolve().parent.parent
    pdf: Path | None = args.pdf
    if pdf is not None:
        pdf = pdf.resolve()
    try:
        run_pipeline(
            project_root,
            from_stage1=args.from_stage1,
            heygen_only=args.heygen_only,
            no_heygen=args.no_heygen,
            course_title=args.course_title,
            pdf=pdf,
            num_modules=args.num_modules,
            duration_hours=args.duration_hours,
            force_heygen=args.force_heygen,
            force_stage1=args.force_stage1,
        )
    except PipelineError as e:
        print(e, file=sys.stderr)
        raise SystemExit(e.exit_code) from e
    except ValueError as e:
        print(e, file=sys.stderr)
        raise SystemExit(2) from e

    if args.heygen_only:
        print("\nStage 5 done (HeyGen only).")
    elif args.no_heygen:
        print("\nStage 5 done (--no-heygen: skipped HeyGen).")
    else:
        print("\nStage 5 full course batch finished.")


if __name__ == "__main__":
    main()
