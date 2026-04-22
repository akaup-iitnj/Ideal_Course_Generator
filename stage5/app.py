"""
Stage 5 web UI: FastAPI + HTML form + JSON polling (no SSE).

  pip install -r requirements.txt
  python -m uvicorn app:app --host 0.0.0.0 --port 8755

Open http://127.0.0.1:8755/ locally. To share with someone off your machine, run a tunnel to port 8755
(Cloudflare: `cloudflared tunnel --url http://127.0.0.1:8755`, or ngrok, etc.). The UI shows a
copyable link when the request is not localhost, or set STAGE5_PUBLIC_URL in stage5/.env to your tunnel URL.

Keep API keys only in .env on the machine running the pipeline, not in the browser. Anyone who has the
public link can start jobs on your PC — use tunnel passwords / turn the tunnel off after demos if needed.
"""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from pipeline import PipelineError, run_pipeline, validate_options

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
load_dotenv(HERE / ".env")
templates = Jinja2Templates(directory=str(HERE / "templates"))
app = FastAPI(title="Stage 5 — Course batch")


def _share_url(request: Request) -> str:
    """Public URL to show for sharing (tunnel). Empty when only localhost is in use."""
    env = os.getenv("STAGE5_PUBLIC_URL", "").strip().rstrip("/")
    if env:
        return env
    raw_base = str(request.base_url).rstrip("/")
    parsed = urlparse(raw_base)
    host = (parsed.hostname or "").lower()
    if host in ("127.0.0.1", "localhost", ""):
        return ""
    return raw_base

JOBS: dict[str, dict[str, Any]] = {}
LOCK = threading.Lock()
MAX_LOG = 14_000


class JobCreate(BaseModel):
    course_title: str = "Start Your Own Food Business"
    pdf: str | None = None
    from_stage1: bool = False
    heygen_only: bool = False
    no_heygen: bool = False
    force_heygen: bool = False
    force_stage1: bool = False


def _append_log(jid: str, line: str) -> None:
    with LOCK:
        j = JOBS.get(jid)
        if not j:
            return
        s = (j.get("log") or "") + line + "\n"
        if len(s) > MAX_LOG:
            s = "…(truncated)…\n" + s[-MAX_LOG:]
        j["log"] = s


def _run_job(jid: str, body: JobCreate) -> None:
    with LOCK:
        j = JOBS.get(jid)
        if not j:
            return
        j["status"] = "running"
    pdf_path: Path | None = None
    if body.pdf and body.pdf.strip():
        pdf_path = Path(body.pdf.strip())

    def on_step(name: str) -> None:
        with LOCK:
            if jid in JOBS:
                JOBS[jid]["current_step"] = name

    def logln(msg: str) -> None:
        _append_log(jid, msg)

    try:
        validate_options(
            body.from_stage1, body.heygen_only, body.no_heygen
        )
        run_pipeline(
            ROOT,
            from_stage1=body.from_stage1,
            heygen_only=body.heygen_only,
            no_heygen=body.no_heygen,
            course_title=body.course_title,
            pdf=pdf_path,
            force_heygen=body.force_heygen,
            force_stage1=body.force_stage1,
            on_step=on_step,
            log=logln,
        )
        with LOCK:
            if jid in JOBS:
                JOBS[jid]["status"] = "complete"
                JOBS[jid]["current_step"] = "done"
    except ValueError as e:
        with LOCK:
            if jid in JOBS:
                JOBS[jid]["status"] = "error"
                JOBS[jid]["error"] = str(e)
    except PipelineError as e:
        with LOCK:
            if jid in JOBS:
                JOBS[jid]["status"] = "error"
                JOBS[jid]["error"] = str(e)
    except Exception as e:  # noqa: BLE001
        with LOCK:
            if jid in JOBS:
                JOBS[jid]["status"] = "error"
                JOBS[jid]["error"] = repr(e)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Any:
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "share_url": _share_url(request)},
    )


@app.post("/api/jobs")
async def create_job(body: JobCreate) -> Any:
    try:
        validate_options(
            body.from_stage1, body.heygen_only, body.no_heygen
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    jid = str(uuid.uuid4())
    with LOCK:
        JOBS[jid] = {
            "id": jid,
            "status": "queued",
            "current_step": None,
            "log": "",
            "error": None,
        }
    threading.Thread(
        target=_run_job,
        args=(jid, body),
        daemon=True,
        name=f"job-{jid[:8]}",
    ).start()
    with LOCK:
        return dict(JOBS[jid])


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> Any:
    with LOCK:
        j = JOBS.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return j
