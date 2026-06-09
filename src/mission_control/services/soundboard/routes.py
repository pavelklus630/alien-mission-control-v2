"""Soundboard HTTP routes — preserves the exact v1 contract so existing
control/output pages and OBS sources keep working:

    GET  /  /control      → control.html (GM remote)
    GET  /output          → output.html (OBS Browser Source)
    GET  /state           → playback + voice snapshot (polled at 1 Hz)
    GET  /sounds.json     → ordered category tree (active bank)
    GET  /audio/<relpath> → Range-streamed audio (active bank)
    POST /                → {action, ...} mutates shared state
    GET  /api/sounds      → structured Sound list (v2 editor/upload seam)
    GET  /api/banks       → soundbank list
    POST /api/banks       → create bank {name, description}
    GET  /api/banks/<id>  → full bank manifest
    DELETE /api/banks/<id> → delete custom bank
    POST /api/banks/<id>/activate → switch active bank
    POST /api/banks/<id>/upload   → convert + ingest audio files
"""

from __future__ import annotations

import asyncio
import io
import json
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from ...config import Settings
from ...core.ranges import range_response
from ...core.templating import service_templates
from ...core.uploads import UploadError, safe_join, validate_upload
from . import audio_ingest
from .bank_store import BankStore
from .state import PlaybackState

_templates = service_templates(__file__)

_MAX_UPLOAD_BYTES = 60 * 1024 * 1024  # 60 MB per file


def build_router(settings: Settings, library: BankStore, state: PlaybackState) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    @router.get("/control", response_class=HTMLResponse)
    async def control(request: Request) -> Response:
        return _templates.TemplateResponse(request, "control.html", _page_ctx(settings))

    @router.get("/output", response_class=HTMLResponse)
    async def output(request: Request) -> Response:
        return _templates.TemplateResponse(request, "output.html", _page_ctx(settings))

    @router.get("/editor", response_class=HTMLResponse)
    async def editor(request: Request) -> Response:
        resp = _templates.TemplateResponse(request, "editor.html", _page_ctx(settings))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @router.get("/state")
    async def get_state() -> JSONResponse:
        snap = state.snapshot()
        snap["_bank"] = library.active_id()  # poll-based bank-switch signal
        return JSONResponse(snap)

    @router.get("/sounds.json")
    async def sounds_json() -> JSONResponse:
        return JSONResponse(library.categories())

    @router.get("/api/sounds")
    async def api_sounds() -> JSONResponse:
        """Flat structured list — the seam future editor/upload UIs consume."""
        flat = [s for items in library.categories().values() for s in items]
        return JSONResponse(flat)

    @router.get("/api/banks")
    async def list_banks() -> JSONResponse:
        return JSONResponse(library.list_banks())

    @router.post("/api/banks")
    async def create_bank(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            name = str(body["name"]).strip()
        except Exception:
            return JSONResponse({"error": "name required"}, status_code=400)
        if not name:
            return JSONResponse({"error": "name required"}, status_code=400)
        bank_id = library.create_bank(name, str(body.get("description", "")))
        return JSONResponse({"ok": True, "id": bank_id})

    @router.get("/api/banks/{bank_id}")
    async def get_bank(bank_id: str) -> JSONResponse:
        try:
            return JSONResponse(library.get_bank(bank_id))
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)

    @router.delete("/api/banks/{bank_id}")
    async def delete_bank(bank_id: str) -> JSONResponse:
        try:
            library.delete_bank(bank_id)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=403)
        return JSONResponse({"ok": True})

    @router.post("/api/banks/{bank_id}/activate")
    async def activate_bank(bank_id: str) -> JSONResponse:
        if not library.set_active(bank_id):
            return JSONResponse({"error": "unknown bank"}, status_code=404)
        return JSONResponse({"ok": True, "active": bank_id})

    @router.post("/api/banks/{bank_id}/upload")
    async def upload_sounds(
        bank_id: str,
        request: Request,
    ) -> JSONResponse:
        """Convert + loudness-normalise uploaded audio into a bank.

        Multipart form: ``files`` (one or more), ``category``, ``kind``
        (music|sfx). Each file is transcoded to Opus/.ogg at the project
        target loudness, then registered in the bank manifest.
        """
        if not audio_ingest.converter_available():
            return JSONResponse(
                {"error": "audio converter (ffmpeg) unavailable"}, status_code=503
            )
        form = await request.form()
        # Non-string form values are uploaded files (the concrete UploadFile class
        # returned by request.form() differs between fastapi/starlette versions).
        files = [f for f in form.getlist("files") if not isinstance(f, str)]
        if not files:
            return JSONResponse({"error": "no files"}, status_code=400)
        category = str(form.get("category") or "Atmosphere & FX")
        kind = str(form.get("kind") or "sfx")

        added: list[dict] = []
        errors: list[dict] = []
        for f in files:
            fn = f.filename or "upload"
            data = await f.read(_MAX_UPLOAD_BYTES + 1)
            try:
                validate_upload(
                    filename=fn, size=len(data), content_type=None,
                    allowed_extensions=audio_ingest.INPUT_EXTENSIONS,
                    max_bytes=_MAX_UPLOAD_BYTES,
                )
                ogg, lufs, peak = await asyncio.to_thread(
                    audio_ingest.convert_and_normalize, data, fn, kind, settings
                )
                name = _display_name(fn)
                meta = {"kind": kind, "lufs": lufs, "peak_db": peak}
                rel = library.add_sound(bank_id, category, name, ogg, meta)
                added.append({"path": rel, "name": name, "lufs": lufs})
            except (UploadError, audio_ingest.ConversionError) as exc:
                errors.append({"file": fn, "error": str(exc)})
            except Exception as exc:  # converter/IO failure — report, don't 500
                errors.append({"file": fn, "error": str(exc)})

        return JSONResponse({"ok": not errors, "added": added, "errors": errors})

    @router.post("/api/banks/{bank_id}/meta")
    async def update_bank_meta(bank_id: str, request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        try:
            library.update_bank(bank_id, body)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"ok": True})

    @router.post("/api/banks/{bank_id}/sounds")
    async def update_sound(bank_id: str, request: Request) -> JSONResponse:
        try:
            body = await request.json()
            path = str(body.pop("path"))
        except Exception:
            return JSONResponse({"error": "path required"}, status_code=400)
        try:
            library.update_sound(bank_id, path, body)
        except KeyError:
            return JSONResponse({"error": "sound not found"}, status_code=404)
        return JSONResponse({"ok": True})

    @router.delete("/api/banks/{bank_id}/sounds")
    async def delete_sound(bank_id: str, path: str) -> JSONResponse:
        try:
            library.remove_sound(bank_id, path)
        except KeyError:
            return JSONResponse({"error": "sound not found"}, status_code=404)
        return JSONResponse({"ok": True})

    @router.get("/api/banks/{bank_id}/audio/{file_path:path}")
    async def bank_audio(bank_id: str, file_path: str, request: Request) -> Response:
        """Range-stream a file from a specific bank (editor preview, any bank)."""
        try:
            target = library.bank_file(bank_id, file_path)
        except UploadError:
            return Response(status_code=403)
        return range_response(target, request)

    @router.get("/api/banks/{bank_id}/export")
    async def export_bank(bank_id: str) -> Response:
        """Download a bank as a .sndbank zip (bank.json + audio files)."""
        try:
            manifest = library.get_bank(bank_id)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr("bank.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            for s in manifest.get("sounds", []):
                p = s.get("path")
                if not p:
                    continue
                try:
                    zf.write(library.bank_file(bank_id, p), p)
                except (UploadError, FileNotFoundError, OSError):
                    pass
        buf.seek(0)
        safe = bank_id.replace("/", "_") + ".sndbank"
        return StreamingResponse(
            buf, media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{safe}"'},
        )

    @router.post("/api/import")
    async def import_bank(request: Request) -> JSONResponse:
        """Import a .sndbank (or .zip) into a new custom bank."""
        form = await request.form()
        up = next((f for f in form.getlist("file") if not isinstance(f, str)), None)
        if up is None:
            return JSONResponse({"error": "no file"}, status_code=400)
        data = await up.read(200 * 1024 * 1024)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                manifest = json.loads(zf.read("bank.json"))
                files = {
                    n: zf.read(n)
                    for n in zf.namelist()
                    if n != "bank.json" and not n.endswith("/")
                }
        except (KeyError, zipfile.BadZipFile, ValueError) as exc:
            return JSONResponse({"error": f"invalid .sndbank: {exc}"}, status_code=400)
        bank_id = library.import_bank(manifest, files)
        return JSONResponse({"ok": True, "id": bank_id})

    @router.post("/api/banks/{bank_id}/analyze")
    async def analyze_bank(bank_id: str) -> JSONResponse:
        """Measure every sound's loudness (read-only). Returns a report; does not persist."""
        try:
            manifest = library.get_bank(bank_id)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        target = settings.audio.target_lufs
        report = []
        for s in manifest.get("sounds", []):
            p = s.get("path", "")
            try:
                data = library.bank_file(bank_id, p).read_bytes()
                lufs, peak = await asyncio.to_thread(audio_ingest.analyze_loudness, data)
            except (UploadError, OSError):
                lufs, peak = None, None
            report.append({
                "path": p, "name": s.get("name", p), "lufs": lufs, "peak_db": peak,
                "off": (lufs is not None and abs(lufs - target) > 2.0),
            })
        return JSONResponse({"ok": True, "target_lufs": target, "report": report})

    @router.post("/api/banks/{bank_id}/normalize")
    async def normalize_bank(bank_id: str, request: Request) -> JSONResponse:
        """Re-encode sounds that drift from the target loudness back to it."""
        if not audio_ingest.converter_available():
            return JSONResponse({"error": "converter (ffmpeg) unavailable"}, status_code=503)
        try:
            body = await request.json()
        except Exception:
            body = {}
        threshold = float(body.get("threshold", 1.0))
        try:
            manifest = library.get_bank(bank_id)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        target = settings.audio.target_lufs
        changed, errors = [], []
        for s in list(manifest.get("sounds", [])):
            p = s.get("path", "")
            try:
                data = library.bank_file(bank_id, p).read_bytes()
                lufs, _ = await asyncio.to_thread(audio_ingest.analyze_loudness, data)
                if lufs is not None and abs(lufs - target) <= threshold:
                    continue
                ogg, new_lufs, peak = await asyncio.to_thread(
                    audio_ingest.convert_and_normalize, data, p, s.get("kind", "sfx"), settings
                )
                library.write_sound_bytes(bank_id, p, ogg, {"lufs": new_lufs, "peak_db": peak})
                changed.append({"path": p, "from": lufs, "to": new_lufs})
            except Exception as exc:
                errors.append({"path": p, "error": str(exc)})
        return JSONResponse({"ok": not errors, "changed": changed, "errors": errors})

    @router.get("/audio/{file_path:path}")
    async def audio(file_path: str, request: Request) -> Response:
        try:
            target = safe_join(library.active_root(), file_path)
        except UploadError:
            return Response(status_code=403)
        return range_response(target, request)

    @router.post("/")
    async def command(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)
        if isinstance(body, dict):
            state.apply(body)
        return JSONResponse({"ok": True})

    return router


def _display_name(filename: str) -> str:
    from .repository import clean_name
    from pathlib import Path
    return clean_name(Path(filename).stem)


def _page_ctx(settings: Settings) -> dict[str, object]:
    # Available to templates now; unused by the ported v1 markup, consumed later
    # by editor/upload UI.
    return {
        "enable_uploads": settings.enable_uploads,
        "enable_editors": settings.enable_editors,
    }
