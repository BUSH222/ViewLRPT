from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

load_dotenv()

OBSERVATION_DIR = Path(os.getenv("OBSERVATION_DIR")).resolve()

STATIC_DIR = Path("static").resolve()
PREVIEW_CACHE_DIR = STATIC_DIR / "cache" / "previews"

_PREVIEW_SCALE = 0.5
_PREVIEW_JPEG_QUALITY = 55
_LANCZOS = Image.Resampling.LANCZOS

app = FastAPI(title="ViewLRPT")

STATIC_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory="templates")


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
    return (
        int.from_bytes(header[16:20], "big"),
        int.from_bytes(header[20:24], "big"),
    )


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


# ---------------------------------------------------------------------------
# Preview thumbnails (static/cache/previews/<observation_id>.jpg)
# ---------------------------------------------------------------------------


def _build_preview_image(obs: dict) -> Image.Image | None:
    """
    Build the base image for a preview.

    Preference order:
      1. Channel 4 as-is (single band, grayscale JPEG).
      2. Channels 1 & 2 merged as RGB(2, 2, 1).
      3. Any other available channel as grayscale.
    """
    channels = obs["channels"]
    try:
        if 4 in channels:
            with Image.open(channels[4]) as img:
                base = img.convert("L")
        elif 1 in channels and 2 in channels:
            with Image.open(channels[1]) as r_img:
                r = r_img.convert("L")
            with Image.open(channels[2]) as g_img:
                g = g_img.convert("L")
            if g.size != r.size:
                g = g.resize(r.size, _LANCZOS)
            base = Image.merge("RGB", (g, g, r))
        else:
            fallback = channels[min(channels)]
            with Image.open(fallback) as img:
                base = img.convert("L")
    except Exception:
        return None

    width, height = base.size
    target = (
        max(1, round(width * _PREVIEW_SCALE)),
        max(1, round(height * _PREVIEW_SCALE)),
    )
    if target != base.size:
        base = base.resize(target, _LANCZOS)
    return base


def _get_preview(obs: dict) -> Path | None:
    """Return a path to a cached preview JPEG, generating it if needed."""
    target = PREVIEW_CACHE_DIR / f"{obs['id']}.jpg"
    sources = list(obs["channels"].values())

    if target.is_file():
        try:
            target_mtime = target.stat().st_mtime
            if all(target_mtime >= src.stat().st_mtime for src in sources):
                return target
        except OSError:
            pass

    image = _build_preview_image(obs)
    if image is None:
        return None

    try:
        if image.mode not in ("L", "RGB"):
            image = image.convert("RGB")
        image.save(
            target,
            format="JPEG",
            quality=_PREVIEW_JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )
    except Exception:
        return None
    finally:
        image.close()

    return target


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
# Preview thumbnail
# ---------------------------------------------------------------------------


@app.get("/api/observations/{observation_id}/preview")
def api_observation_preview(observation_id: str):
    obs = _find(observation_id)
    if obs is None:
        raise HTTPException(status_code=404, detail="Observation not found")

    path = _get_preview(obs)
    if path is None:
        raise HTTPException(status_code=404, detail="Preview not available")

    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ---------------------------------------------------------------------------
# Render endpoint
# ---------------------------------------------------------------------------
#
# Payload (all keys optional):
#
#   {
#     "display_mode":      "channel" | "composite" | "custom_composite",
#     "channel":           1-4,               # for display_mode == "channel"
#     "composite":         "<name>",          # for display_mode == "composite"
#     "custom_composite":  "<spec>",          # for display_mode == "custom_composite"
#     "rotate_180":        bool,   # accepted, not yet implemented
#     "geocorrection":     bool,   # accepted, not yet implemented
#     "map":               bool,   # accepted, not yet implemented
#     "labels":            bool    # accepted, not yet implemented
#   }
#
# Composite modes are stubs; they will be wired to external scripts later.


@app.post("/api/observations/{observation_id}/render")
def api_render(observation_id: str, payload: dict | None = None):
    obs = _find(observation_id)
    if obs is None:
        raise HTTPException(status_code=404, detail="Observation not found")

    payload = payload or {}
    display_mode = str(payload.get("display_mode") or "channel").lower()

    # Accepted for API stability, not yet implemented.
    _rotate_180 = bool(payload.get("rotate_180"))
    _geocorrection = bool(payload.get("geocorrection"))
    _map = bool(payload.get("map"))
    _labels = bool(payload.get("labels"))

    if display_mode == "channel":
        try:
            channel = int(payload.get("channel") or 1)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid channel") from exc

        if channel not in (1, 2, 3, 4):
            raise HTTPException(status_code=400, detail="Channel must be 1, 2, 3, or 4")

        path = obs["channels"].get(channel)
        if path is None:
            raise HTTPException(status_code=404, detail=f"Channel {channel} not available")

        return FileResponse(path, media_type="image/png")

    if display_mode in ("composite", "custom_composite"):
        raise HTTPException(status_code=501, detail="Composite rendering not yet implemented")

    raise HTTPException(status_code=400, detail=f"Unknown display_mode '{display_mode}'")
