"""
Stage 3: script.json + slide PNGs -> one HeyGen video (avatar + text, slide as background, bottom-right offset).
Uses POST /v2/video/generate and GET /v1/video_status.get. Keys in stage3/.env (HEYGEN_API_KEY).

Optional: HEYGEN_POLL_TIMEOUT_MINUTES (default 120). Long multi-scene videos can exceed 45 minutes; the
older 45 min cap caused spurious timeouts.

By default, runs stage1 `make_video.py --from-json` first so stage1/output matches this script
(slides + TTS + local MP4). Use --skip-stage1 to use existing slide_*.png in --slides-dir only.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

API = "https://api.heygen.com"
UPLOAD = "https://upload.heygen.com"
MAX_TEXT_PER_SCENE = 5000
# 720p = 1280x720; avatar nudged toward bottom-right (HeyGen: 0,0 centers the character)
DEFAULT_DIM = {"width": 1280, "height": 720}
DEFAULT_SCALE = 0.42
DEFAULT_OFF = {"x": 0.38, "y": 0.32}


def _here() -> Path:
    return Path(__file__).resolve().parent


def _stage1_output_dir() -> Path:
    return _here().parent / "stage1" / "output"


def _regenerate_stage1(script_path: Path) -> None:
    """
    Rebuild stage1/output (slide PNGs, MP3s, output.mp4) from this script so slide counts always match.
    subprocess + cwd=stage1: same as running `python make_video.py --from-json ...` in that folder.
    """
    stage1 = _here().parent / "stage1"
    make = stage1 / "make_video.py"
    if not make.is_file():
        raise SystemExit(
            f"Expected stage1 at {stage1} (with make_video.py) to regenerate slides."
        )
    sp = script_path.resolve()
    print(f"Regenerating stage1 from script (this uses OpenAI TTS + LibreOffice) ...\n  {sp}\n")
    r = subprocess.run(
        [sys.executable, str(make), "--from-json", str(sp)],
        cwd=str(stage1),
    )
    if r.returncode != 0:
        raise SystemExit("stage1 make_video.py --from-json failed; see messages above.")
    print("stage1 output updated.\n")


def _load_env_key() -> str:
    from dotenv import load_dotenv

    for p in (_here() / ".env", _here().parent / "stage2" / ".env"):
        if p.is_file():
            load_dotenv(p, override=True)
    k = (os.environ.get("HEYGEN_API_KEY") or "").strip()
    if not k:
        raise SystemExit("Set HEYGEN_API_KEY in stage3/.env (UTF-8, no BOM).")
    return k


def _headers(key: str) -> dict[str, str]:
    return {"x-api-key": key, "Accept": "application/json"}


def _norm_gender(s: str | None) -> str:
    if not s:
        return ""
    t = str(s).strip().lower()
    if t in ("female", "f", "woman", "w"):
        return "female"
    if t in ("male", "m", "man"):
        return "male"
    return t


def list_matched_avatar_voice(key: str) -> tuple[str, str]:
    """
    Pick avatar + voice that go together: prefer the avatar's default_voice_id from the API;
    else first voice whose gender field matches the avatar's gender; else first+first.
    """
    h = _headers(key)
    with httpx.Client(timeout=60.0) as c:
        ra = c.get(f"{API}/v2/avatars", headers=h)
        ra.raise_for_status()
        ja = ra.json()
        if ja.get("error"):
            raise RuntimeError(f"List avatars: {ja}")
        avatars = (ja.get("data") or {}).get("avatars") or []
        if not avatars:
            raise RuntimeError("No avatars returned; check your HeyGen plan/API key.")
        # Prefer first non-premium avatar if the flag exists (skip paywalled in some accounts)
        av0: dict | None = None
        for av in avatars:
            if not av.get("premium", False):
                av0 = av
                break
        if av0 is None:
            av0 = avatars[0]
        aid = str(av0["avatar_id"])
        a_name = str(av0.get("avatar_name", aid))
        ag = _norm_gender(av0.get("gender"))

        rv = c.get(f"{API}/v2/voices", headers=h)
        rv.raise_for_status()
        jv = rv.json()
        if jv.get("error"):
            raise RuntimeError(f"List voices: {jv}")
        voices = (jv.get("data") or {}).get("voices") or []
        if not voices:
            raise RuntimeError("No voices returned.")

        vid: str | None = None
        v_name: str = ""
        dvid = av0.get("default_voice_id")
        if dvid and str(dvid).strip():
            dvid = str(dvid).strip()
            for v in voices:
                if str(v.get("voice_id", "")).strip() == dvid:
                    vid = dvid
                    v_name = str(v.get("name", dvid))
                    break
        if not vid and ag in ("male", "female"):
            for v in voices:
                vg = _norm_gender(v.get("gender") or v.get("sex") or v.get("gender_type"))
                if vg and vg == ag:
                    vid = str(v["voice_id"])
                    v_name = str(v.get("name", vid))
                    break
        if not vid:
            v0 = voices[0]
            vid = str(v0["voice_id"])
            v_name = str(v0.get("name", vid))

    print("Auto-selected avatar + voice (or set HEYGEN_AVATAR_ID / HEYGEN_VOICE_ID in .env):")
    print(f"  AVATAR  {aid}  ({a_name})  [gender: {ag or 'unspecified'}]")
    print(f"  VOICE   {vid}  ({v_name})  [matched to avatar]")
    return aid, str(vid)


def upload_image_file(key: str, path: Path) -> dict[str, str | None]:
    """
    Returns asset id and URL from HeyGen. For /v2/video/generate, image backgrounds should use
    **either** url **or** image_asset_id (not both) — we prefer url when the API returns it; that
    often fixes blank backgrounds when id-only was ignored by the render pipeline.
    """
    data = path.read_bytes()
    suf = path.suffix.lower()
    if suf in (".png",):
        ct = "image/png"
    elif suf in (".jpg", ".jpeg"):
        ct = "image/jpeg"
    else:
        raise ValueError(f"Unsupported image: {path}")
    h = {"x-api-key": key, "Content-Type": ct}
    with httpx.Client(timeout=120.0) as c:
        r = c.post(f"{UPLOAD}/v1/asset", headers=h, content=data)
        r.raise_for_status()
    j = r.json()
    if j.get("error"):
        raise RuntimeError(f"Upload error: {j}")
    d = j.get("data") or {}
    aid = d.get("id")
    u = d.get("url") or d.get("file_url")
    if u is not None:
        u = str(u).strip() or None
    if not aid and not u:
        raise RuntimeError(f"Upload missing id and url: {j}")
    return {"asset_id": str(aid) if aid else None, "url": u}


def _float_env(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return float(raw)


def _offset() -> dict[str, float]:
    return {
        "x": _float_env("HEYGEN_OFFSET_X", DEFAULT_OFF["x"]),
        "y": _float_env("HEYGEN_OFFSET_Y", DEFAULT_OFF["y"]),
    }


def _bg_fit() -> str | None:
    """Optional; docs often describe `fit` for video backgrounds — set HEYGEN_BG_FIT only if image works with it."""
    s = (os.environ.get("HEYGEN_BG_FIT") or "").strip().lower()
    if s in ("cover", "contain", "none", "crop"):
        return s
    return None


def _resolve_ids(key: str) -> tuple[str, str]:
    aid = (os.environ.get("HEYGEN_AVATAR_ID") or "").strip()
    vid = (os.environ.get("HEYGEN_VOICE_ID") or "").strip()
    if aid and vid:
        return aid, vid
    print("HEYGEN_AVATAR_ID and/or HEYGEN_VOICE_ID missing; resolving from API ...")
    a_def, v_def = list_matched_avatar_voice(key)
    return (aid or a_def, vid or v_def)


def build_video_inputs(
    slides: list[dict[str, Any]],
    image_uploads: list[dict[str, str | None]],
    avatar_id: str,
    voice_id: str,
    scale: float,
    offset: dict[str, float],
) -> list[dict[str, Any]]:
    if len(slides) != len(image_uploads):
        raise ValueError("slides / image uploads length mismatch")
    fit = _bg_fit()
    out: list[dict[str, Any]] = []
    for slide, uinfo in zip(slides, image_uploads, strict=True):
        text = (slide.get("narration") or "").strip()
        if len(text) > MAX_TEXT_PER_SCENE:
            print(
                f"  Warning: truncating scene text from {len(text)} to {MAX_TEXT_PER_SCENE} chars"
            )
            text = text[:MAX_TEXT_PER_SCENE]
        if not text:
            raise ValueError("Empty narration in slide; HeyGen text voice needs non-empty text.")
        # API: provide url XOR image_asset_id. Prefer CDN url from upload response.
        url = (uinfo.get("url") or None) and str(uinfo["url"]).strip()
        aid = (uinfo.get("asset_id") or None) and str(uinfo["asset_id"]).strip()
        bg: dict[str, Any] = {"type": "image"}
        if fit:
            bg["fit"] = fit
        if url:
            bg["url"] = url
        elif aid:
            bg["image_asset_id"] = aid
        else:
            raise ValueError("Each slide image upload must include url or asset_id")
        out.append(
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "scale": scale,
                    "offset": offset,
                },
                "voice": {
                    "type": "text",
                    "voice_id": voice_id,
                    "input_text": text,
                },
                "background": bg,
            }
        )
    return out


def create_video(
    key: str,
    video_inputs: list[dict[str, Any]],
    title: str,
) -> str:
    body: dict[str, Any] = {
        "title": title[:200],
        "video_inputs": video_inputs,
        "dimension": {**DEFAULT_DIM},
    }
    h = {**_headers(key), "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{API}/v2/video/generate", headers=h, json=body)
        if r.status_code != 200:
            raise RuntimeError(
                f"create video HTTP {r.status_code}: {r.text[:2000]}"
            )
        j = r.json()
    if j.get("error"):
        raise RuntimeError(f"HeyGen: {j}")
    vid = (j.get("data") or {}).get("video_id")
    if not vid:
        raise RuntimeError(f"Missing video_id: {j}")
    return str(vid)


def _fmt_elapsed(secs: float) -> str:
    m, s = int(secs // 60), int(secs % 60)
    return f"{m:02d}:{s:02d}"


def _poll_interval_sec(elapsed: float) -> float:
    return 5.0 if elapsed < 120.0 else 15.0


def _poll_timeout_sec() -> float:
    """Max wait for one render job (multi-scene lessons can take over 45 minutes)."""
    raw = (os.environ.get("HEYGEN_POLL_TIMEOUT_MINUTES") or "").strip()
    if not raw:
        return 120.0 * 60.0
    try:
        minutes = int(raw, 10)
    except ValueError:
        return 120.0 * 60.0
    return max(60.0, float(minutes) * 60.0)


def poll_until_done(key: str, video_id: str) -> str:
    h = _headers(key)
    t0 = time.time()
    timeout_sec = _poll_timeout_sec()
    timeout_min = int(timeout_sec // 60)
    last_status: str | None = None
    last_heartbeat = -1.0
    n = 0
    while time.time() - t0 < timeout_sec:
        elapsed = time.time() - t0
        sleep_for = _poll_interval_sec(elapsed)
        with httpx.Client(timeout=60.0) as c:
            r = c.get(
                f"{API}/v1/video_status.get",
                params={"video_id": video_id},
                headers=h,
            )
            r.raise_for_status()
            j = r.json()
        data = j.get("data")
        if data is None and isinstance(j, dict):
            data = j
        st = (data or {}).get("status")
        if isinstance(st, dict):
            st = st.get("name") or st.get("value")
        st = (st or "").lower() if isinstance(st, str) else str(st)
        err_blob = (data or {}).get("error") if data else None
        if err_blob and str(err_blob).strip() not in ("", "null", "None"):
            print(
                f"  elapsed={_fmt_elapsed(elapsed)} status={st} API error in payload:\n{str(j)[:2000]}"
            )

        if isinstance(data, dict) and n == 0:
            print(
                "  Note: HeyGen's published /v1/video_status.get schema has no progress-percent field; "
                "the dashboard % may use internal/WebSocket data. If the API ever returns extra "
                "fields, they are printed below when present; use HEYGEN_LOG_STATUS_DEBUG=1 for full data."
            )
            for cand in (
                "progress",
                "percent",
                "percentage",
                "render_progress",
                "queue_position",
            ):
                if cand in data:
                    print(f"  (status data includes {cand!r}={data.get(cand)!r})")
            if (os.environ.get("HEYGEN_LOG_STATUS_DEBUG") or "").strip().lower() in (
                "1",
                "true",
                "yes",
            ):
                print(f"  HEYGEN_LOG_STATUS_DEBUG data: {str(data)[:2500]}")

        if st in ("completed", "complete", "success"):
            url = (data or {}).get("video_url")
            if not url:
                url = (data or {}).get("url")
            if not url and isinstance(j, dict):
                url = j.get("video_url")
            if not url:
                raise RuntimeError(f"Completed but no video_url: {j}")
            print(f"  done after {_fmt_elapsed(time.time() - t0)}")
            return str(url)
        if st in ("failed", "error", "canceled", "cancelled"):
            print(f"  failed payload (first 2k): {str(j)[:2000]}")
            err = (data or {}).get("error", j)
            raise RuntimeError(f"Video final status: {st} - {err}")

        # Quiet mode: one line on status change; then heartbeat every ~90s; dump raw on change
        if st != last_status:
            if last_status is not None:
                print(
                    f"  status: {last_status!r} -> {st!r}  (elapsed={_fmt_elapsed(elapsed)})"
                )
                j_snip = (str(j) if j else "")[:800].replace("\n", " ")
                print(f"  detail: {j_snip!r} ...")
            else:
                print(
                    f"  elapsed={_fmt_elapsed(elapsed)} status={st}  (5s poll <2min, then 15s; long jobs are normal)"
                )
            last_status = st
            last_heartbeat = elapsed
        elif elapsed - last_heartbeat >= 90.0:
            print(
                f"  still {st}  elapsed={_fmt_elapsed(elapsed)}  (no per-% progress in this API response)"
            )
            last_heartbeat = elapsed
        n += 1
        time.sleep(sleep_for)
    raise TimeoutError(
        f"HeyGen did not complete within {timeout_min} minutes "
        f"(set HEYGEN_POLL_TIMEOUT_MINUTES in stage3/.env to wait longer)."
    )


def download_mp4(url: str, out: Path) -> None:
    with httpx.Client(timeout=300.0, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
    out.write_bytes(r.content)
    print(f"Saved {out.resolve()} ({len(r.content)} bytes)")


def run(
    script_path: Path,
    slides_dir: Path,
    out_path: Path,
    skip_stage1: bool,
) -> None:
    if not skip_stage1:
        _regenerate_stage1(script_path)
    key = _load_env_key()
    script: dict[str, Any] = json.loads(script_path.read_text(encoding="utf-8"))
    topic = str(script.get("topic") or "Lesson")
    slides = list(script.get("slides") or [])
    if not slides:
        raise SystemExit("No slides in script.json")

    uploads: list[dict[str, str | None]] = []
    for s in slides:
        n = int(s.get("slide_num", 0))
        if n < 1:
            raise SystemExit("Invalid slide_num in script")
        png = slides_dir / f"slide_{n:02d}.png"
        if not png.is_file():
            raise SystemExit(
                f"Missing {png} - run stage1 to render slides for this script, or set --slides-dir."
            )
        print(f"Uploading {png.name} ...")
        u = upload_image_file(key, png)
        uploads.append(u)
        if u.get("url"):
            print(f"  (got upload url: {str(u['url'])[:64]}... )")
        else:
            print(f"  (upload asset_id only, no url; using image_asset_id)")

    scale = _float_env("HEYGEN_AVATAR_SCALE", DEFAULT_SCALE)
    off = _offset()
    av, vo = _resolve_ids(key)
    vinputs = build_video_inputs(
        slides, uploads, av, vo, scale, off
    )
    print(
        f"Creating HeyGen video: {len(vinputs)} scene(s), 720p, avatar offset {off}, scale {scale} ..."
    )
    job = create_video(key, vinputs, title=topic)
    print(f"  video_id={job} (rendering; this can take several minutes) ...")
    url = poll_until_done(key, job)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    download_mp4(url, out_path)


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Stage3: script.json + slide_*.png -> one HeyGen MP4 (avatar bottom-right, 720p)."
    )
    p.add_argument(
        "--script",
        type=Path,
        default=None,
        help="Path to script.json (default: ../stage2/output/script.json)",
    )
    p.add_argument(
        "--slides-dir",
        type=Path,
        default=None,
        help="Folder with slide_01.png ... (default: ../stage1/output/)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: output/lesson_heygen.mp4)",
    )
    p.add_argument(
        "--list-ids",
        action="store_true",
        help="Print first avatar and voice from API, then exit.",
    )
    p.add_argument(
        "--skip-stage1",
        action="store_true",
        help="Do not run stage1 --from-json; you must already have slide_*.png in --slides-dir.",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    here = _here()
    if args.list_ids:
        k = _load_env_key()
        list_matched_avatar_voice(k)
        raise SystemExit(0)

    script = args.script or (here.parent / "stage2" / "output" / "script.json")
    if not args.skip_stage1 and args.slides_dir is not None:
        print(
            "Note: --slides-dir is ignored when stage1 is auto-refreshed; using stage1\\output\\",
            file=sys.stderr,
        )
    sdir: Path
    if not args.skip_stage1:
        sdir = _stage1_output_dir()
    else:
        sdir = args.slides_dir or (here.parent / "stage1" / "output")
    outp = args.out or (here / "output" / "lesson_heygen.mp4")
    if not script.is_file():
        raise SystemExit(
            f"Script not found: {script}\nUse --script or place stage2 output at ../stage2/output/script.json"
        )
    if args.skip_stage1 and not sdir.is_dir():
        raise SystemExit(
            f"Slides dir not found: {sdir}.\n"
            "Omit --skip-stage1 to run stage1 first, or add slide_*.png to that folder."
        )
    run(script, sdir, outp, skip_stage1=bool(args.skip_stage1))
