"""
Shared full-course batch (stage4 -> batch_stage1 -> batch_stage3). Used by run_stage5.py and the web UI.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


class PipelineError(Exception):
    """Subprocess step failed."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        self.exit_code = exit_code
        super().__init__(message)


def stage4_dir(project_root: Path) -> Path:
    return project_root / "stage4"


def _run_subprocess(
    args: list[str],
    cwd: Path,
    label: str,
    *,
    log: Callable[[str], None] | None = None,
) -> None:
    line = f"\n{'='*60}\n{label}\n{'='*60}\n$ {' '.join(args)}"
    if log:
        log(line)
    else:
        print(line, flush=True)
    r = subprocess.run(args, cwd=str(cwd), check=False)
    if r.returncode != 0:
        raise PipelineError(
            f"{label} failed with exit code {r.returncode}", exit_code=r.returncode
        )


def run_pipeline(
    project_root: Path,
    *,
    from_stage1: bool = False,
    heygen_only: bool = False,
    no_heygen: bool = False,
    course_title: str = "Start Your Own Food Business",
    pdf: Path | None = None,
    num_modules: int = 5,
    duration_hours: int = 1,
    force_heygen: bool = False,
    force_stage1: bool = False,
    on_step: Callable[[str], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> None:
    s4 = stage4_dir(project_root)
    py = sys.executable
    run4 = s4 / "run_stage4.py"
    b1 = s4 / "batch_stage1.py"
    b3 = s4 / "batch_stage3.py"
    for p in (run4, b1, b3):
        if not p.is_file():
            raise PipelineError(f"Missing: {p}", exit_code=2)

    if heygen_only and from_stage1:
        raise ValueError("Use only one of heygen_only or from_stage1")
    if heygen_only and no_heygen:
        raise ValueError("Cannot combine heygen_only with no_heygen")

    if heygen_only:
        if on_step:
            on_step("batch_stage3")
        cmd3 = [str(py), str(b3)]
        if force_heygen:
            cmd3.append("--force")
        _run_subprocess(cmd3, s4, "batch_stage3 (HeyGen, all lessons)", log=log)
        return

    if not from_stage1:
        if on_step:
            on_step("run_stage4")
        cmd4 = [str(py), str(run4), "--all-scripts", "--course-title", course_title]
        cmd4.extend(["--num-modules", str(int(num_modules))])
        cmd4.extend(["--duration-hours", str(int(duration_hours))])
        if pdf is not None:
            pr = pdf.resolve()
            if not pr.is_file():
                raise PipelineError(f"PDF not found: {pr}", exit_code=2)
            cmd4.extend(["--pdf", str(pr)])
        _run_subprocess(
            cmd4, s4, "run_stage4 (extract + outline + per-lesson script.json)", log=log
        )

    if on_step:
        on_step("batch_stage1")
    cmd1 = [str(py), str(b1)]
    if force_stage1:
        cmd1.append("--force")
    _run_subprocess(cmd1, s4, "batch_stage1 (all lessons -> output.mp4)", log=log)

    if no_heygen:
        return

    if on_step:
        on_step("batch_stage3")
    cmd3 = [str(py), str(b3)]
    if force_heygen:
        cmd3.append("--force")
    _run_subprocess(
        cmd3, s4, "batch_stage3 (HeyGen -> lesson_heygen.mp4)", log=log
    )


def validate_options(
    from_stage1: bool,
    heygen_only: bool,
    no_heygen: bool,
) -> None:
    if heygen_only and from_stage1:
        raise ValueError("Use only one of heygen-only or from-stage1")
    if heygen_only and no_heygen:
        raise ValueError("Cannot combine heygen-only with no-heygen")
