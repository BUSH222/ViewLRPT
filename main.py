"""Minimal FastAPI backend for the ViewLRPT templates, backed by real observations.

Scans OBSERVATION_DIR (from .env) for folders laid out like:

    <prefix>_<YYYYmmddTHHMMSSZ>_<norad>/
        satdump_output/
            dataset.json
            MSU-MR/
                MSU-MR-1.png
                MSU-MR-2.png
                ...

Only folders that have a satdump_output/MSU-MR directory containing at
least one MSU-MR-<n>.png are exposed. The line count is the height (in
pixels) of the channel 1 image, read straight from the PNG header.

Image endpoints always return channel 1. The only transform kept is
rotate_180.
"""

from __future__ import annotations

import io
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

OBSERVATION_DIR = Path(os.getenv("OBSERVATION_DIR", "./observations")).expanduser().resolve()

app = FastAPI(title="ViewLRPT")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Observation scanning
# ---------------------------------------------------------------------------

_FOLDER_RE = re.compile(r"^(?P<prefix>\d+)_(?P<stamp>\d{8}T\d{6}Z)_(?P<norad>\d+)$")
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png_size(path: Path) -> tuple[int, int] | None:
    """Read (width, height) straight from a PNG's IHDR chunk."""
    try:
        with path.open("rb") as fh:
            header = fh.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != _PNG_SIG or header[12:16] != b"IHDR":
        return None
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return width, height


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scan_observations() -> list[dict]:
    results: list[dict] = []
    if not OBSERVATION_DIR.is_dir():
        return results

    for entry in sorted(OBSERVATION_DIR.iterdir()):
        if not entry.is_dir():
            continue

        match = _FOLDER_RE.match(entry.name)
        if not match:
            continue

        satdump_dir = entry / "satdump_output"
        msur_dir = satdump_dir / "MSU-MR"
        dataset_path = satdump_dir / "dataset.json"

        if not msur_dir.is_dir():
            continue

        channels: dict[int, Path] = {}
        for channel in (1, 2, 3, 4):
            candidate = msur_dir / f"MSU-MR-{channel}.png"
            if candidate.is_file():
                channels[channel] = candidate

        # Omit observations that have no channel images at all.
        if not channels:
            continue

        primary = channels.get(1) or next(iter(channels.values()))
        dims = _png_size(primary)
        if dims is None:
            continue
        line_count = dims[1]

        satellite: str | None = None
        timestamp_utc: str | None = None
        if dataset_path.is_file():
            try:
                dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
                satellite = dataset.get("satellite")
                ts = dataset.get("timestamp")
                if isinstance(ts, (int, float)):
                    timestamp_utc = _iso_utc(datetime.fromtimestamp(ts, tz=UTC))
            except OSError, json.JSONDecodeError, ValueError, OverflowError:
                pass

        if not satellite:
            satellite = "Unknown satellite"
        if not timestamp_utc:
            try:
                stamp = datetime.strptime(match.group("stamp"), "%Y%m%dT%H%M%SZ")
                timestamp_utc = _iso_utc(stamp.replace(tzinfo=UTC))
            except ValueError:
                timestamp_utc = ""

        results.append(
            {
                "id": entry.name,
                "satellite_name": satellite,
                "norad_id": int(match.group("norad")),
                "timestamp_utc": timestamp_utc,
                "line_count": line_count,
                "channels": channels,
            }
        )

    results.sort(key=lambda item: item["timestamp_utc"] or "", reverse=True)
    return results


_cache: list[dict] | None = None


def _observations() -> list[dict]:
    global _cache
    if _cache is None:
        _cache = _scan_observations()
    return _cache


def _find(observation_id: str) -> dict | None:
    for obs in _observations():
        if obs["id"] == observation_id:
            return obs
    return None


def _public_view(obs: dict) -> dict:
    return {
        "id": obs["id"],
        "satellite_name": obs["satellite_name"],
        "norad_id": obs["norad_id"],
        "timestamp_utc": obs["timestamp_utc"],
        "line_count": obs["line_count"],
        "channels": sorted(obs["channels"].keys()),
    }


def _channel_one_path(obs: dict) -> Path | None:
    """Return the channel 1 PNG, falling back to the first available one."""
    if 1 in obs["channels"]:
        return obs["channels"][1]
    if obs["channels"]:
        return obs["channels"][min(obs["channels"])]
    return None


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, name="index")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/observation", response_class=HTMLResponse, name="observation")
async def observation(request: Request, id: str = ""):
    """Used by `url_for('observation')` in index.html — accepts ?id=<folder>."""
    obs_list = _observations()
    default_id = obs_list[0]["id"] if obs_list else ""
    return templates.TemplateResponse(
        request=request,
        name="observation.html",
        context={"observation_id": id or default_id},
    )


@app.get(
    "/observations/{observation_id}",
    response_class=HTMLResponse,
    name="observation_detail",
)
async def observation_detail(request: Request, observation_id: str):
    return templates.TemplateResponse(
        request=request,
        name="observation.html",
        context={"observation_id": observation_id},
    )


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------


@app.get("/api/observations")
async def api_observations():
    return {"items": [_public_view(o) for o in _observations()]}


@app.get("/api/observations/{observation_id}")
async def api_observation(observation_id: str):
    obs = _find(observation_id)
    if obs is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return {"item": _public_view(obs)}


@app.post("/api/reload")
async def api_reload():
    """Re-scan OBSERVATION_DIR without restarting the server."""
    global _cache
    _cache = None
    return {"items": len(_observations())}


# ---------------------------------------------------------------------------
# Channel image endpoint — always serves channel 1
# ---------------------------------------------------------------------------


@app.get("/api/observations/{observation_id}/channels/{channel}")
def api_channel_image(observation_id: str, channel: int, size: str = "full"):
    obs = _find(observation_id)
    if obs is None:
        raise HTTPException(status_code=404, detail="Observation not found")

    path = _channel_one_path(obs)
    if path is None:
        raise HTTPException(status_code=404, detail="No channels available")

    return FileResponse(path, media_type="image/png")


# ---------------------------------------------------------------------------
# Render endpoint — channel 1, optional rotate_180 only
# ---------------------------------------------------------------------------


@app.post("/api/observations/{observation_id}/render")
def api_render(observation_id: str, payload: dict | None = None):
    obs = _find(observation_id)
    if obs is None:
        raise HTTPException(status_code=404, detail="Observation not found")

    payload = payload or {}
    rotate = bool(payload.get("rotate_180"))

    path = _channel_one_path(obs)
    if path is None:
        raise HTTPException(status_code=404, detail="No channels available")

    # No transformation requested: stream the file directly.
    if not rotate:
        return FileResponse(path, media_type="image/png")

    try:
        with Image.open(path) as img:
            rotated = img.rotate(180)
            buf = io.BytesIO()
            rotated.save(buf, format="PNG")
    except Exception:
        return FileResponse(path, media_type="image/png")

    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=60"},
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "observation_dir": str(OBSERVATION_DIR),
        "observations": len(_observations()),
    }
