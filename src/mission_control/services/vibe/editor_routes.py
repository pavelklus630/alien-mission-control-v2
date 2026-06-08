"""Editor HTTP routes for the vibe scene editor.

    GET  /editor                           → editor SPA
    GET  /api/editor/scenes                → list all scenes (builtin + custom)
    GET  /api/editor/scenes/{scene_id}     → full scene JSON
    POST /api/editor/scenes/{scene_id}     → save / create custom scene
    DELETE /api/editor/scenes/{scene_id}   → delete custom scene
    GET  /api/editor/scenes/{scene_id}/export → download .vibe ZIP
    POST /api/editor/import                → upload .vibe or .json
    GET  /api/editor/assets                → list uploaded assets
    POST /api/editor/assets                → upload image asset
    GET  /api/editor/assets/{filename}     → serve asset file
    DELETE /api/editor/assets/{filename}   → delete asset
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from ...config import Settings
from ...core.uploads import UploadError
from .asset_store import AssetStore
from .scene_store import SceneNotFound, SceneStore

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_MAX_IMPORT_BYTES = 50 * 1024 * 1024  # 50 MB


def build_editor_router(
    settings: Settings,
    scenes: SceneStore,
    assets: AssetStore,
) -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------------ SPA
    @router.get("/editor")
    async def editor_page() -> Response:
        return FileResponse(
            _TEMPLATES / "editor.html",
            media_type="text/html",
            headers={"Cache-Control": "no-store"},
        )

    # ------------------------------------------------------------------ scene list / CRUD
    @router.get("/api/editor/scenes")
    async def list_scenes() -> JSONResponse:
        return JSONResponse(scenes.list_all())

    @router.get("/api/editor/scenes/{scene_id}/export")
    async def export_scene(scene_id: str) -> Response:
        try:
            scene = scenes.get(scene_id)
        except SceneNotFound:
            return JSONResponse({"error": "not found"}, status_code=404)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("scene.json", json.dumps(scene, indent=2, ensure_ascii=False))
            for fn in _collect_asset_refs(scene):
                try:
                    zf.write(assets.path_for(fn), f"assets/{fn}")
                except FileNotFoundError:
                    pass

        buf.seek(0)
        safe_name = scene_id.replace("/", "_") + ".vibe"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
        )

    @router.get("/api/editor/scenes/{scene_id}")
    async def get_scene(scene_id: str) -> JSONResponse:
        try:
            return JSONResponse(scenes.get(scene_id))
        except SceneNotFound:
            return JSONResponse({"error": "not found"}, status_code=404)

    @router.post("/api/editor/scenes/{scene_id}")
    async def save_scene(scene_id: str, request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        body["id"] = scene_id
        try:
            scenes.save(body)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"ok": True})

    @router.delete("/api/editor/scenes/{scene_id}")
    async def delete_scene(scene_id: str) -> JSONResponse:
        try:
            scenes.delete(scene_id)
        except SceneNotFound:
            return JSONResponse({"error": "not found"}, status_code=404)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=403)
        return JSONResponse({"ok": True})

    # ------------------------------------------------------------------ import
    @router.post("/api/editor/import")
    async def import_scene(file: UploadFile) -> JSONResponse:
        data = await file.read(_MAX_IMPORT_BYTES)
        filename = file.filename or ""
        scene: dict | None = None

        if filename.endswith(".json"):
            try:
                scene = json.loads(data)
            except Exception:
                return JSONResponse({"error": "invalid JSON"}, status_code=400)
        elif filename.endswith(".vibe"):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    scene = json.loads(zf.read("scene.json"))
                    for name in zf.namelist():
                        if name.startswith("assets/") and name != "assets/":
                            asset_bytes = zf.read(name)
                            asset_fn = Path(name).name
                            try:
                                assets.save(asset_fn, asset_bytes)
                            except (UploadError, Exception):
                                pass
            except (KeyError, zipfile.BadZipFile) as exc:
                return JSONResponse({"error": f"invalid .vibe archive: {exc}"}, status_code=400)
        else:
            return JSONResponse(
                {"error": "unsupported format — use .json or .vibe"}, status_code=400
            )

        if not isinstance(scene, dict) or "id" not in scene:
            return JSONResponse(
                {"error": "scene JSON must have an 'id' field"}, status_code=400
            )
        try:
            scenes.save(scene)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        return JSONResponse({"ok": True, "id": scene["id"]})

    # ------------------------------------------------------------------ assets
    @router.get("/api/editor/assets")
    async def list_assets() -> JSONResponse:
        return JSONResponse(assets.list_assets())

    @router.post("/api/editor/assets")
    async def upload_asset(file: UploadFile) -> JSONResponse:
        data = await file.read()
        try:
            assets.save(file.filename or "upload.png", data, file.content_type)
        except UploadError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "filename": file.filename})

    @router.get("/api/editor/assets/{filename}")
    async def serve_asset(filename: str) -> Response:
        try:
            path = assets.path_for(filename)
        except FileNotFoundError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(str(path))

    @router.delete("/api/editor/assets/{filename}")
    async def delete_asset(filename: str) -> JSONResponse:
        try:
            assets.delete(filename)
        except FileNotFoundError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"ok": True})

    return router


def _collect_asset_refs(scene: dict) -> list[str]:
    refs: list[str] = []
    for layer in scene.get("layers", []):
        params = layer.get("params", {})
        for key in ("asset", "src", "filename", "image"):
            val = params.get(key)
            if isinstance(val, str) and val:
                refs.append(val)
    return refs
