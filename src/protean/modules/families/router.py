from pathlib import Path

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from protean.modules.families import export, store
from protean.modules.families.api_schemas import FamilyOut, FamilySummary, Name

router = APIRouter(prefix="/families", tags=["families"])


@router.get("", response_model=list[FamilySummary])
async def list_families() -> list[FamilySummary]:
    """Saved families, most recently saved first."""
    return store.list_families()


@router.get("/{name}", response_model=FamilyOut)
async def get_family(name: Name) -> FamilyOut:
    return store.read(name)


@router.get("/{name}/export")
async def export_family(name: Name) -> FileResponse:
    """The saved family folder as a zip download."""
    zipped = export.build(name)
    return FileResponse(
        zipped,
        media_type="application/zip",
        filename=f"{name}.zip",
        background=BackgroundTask(Path.unlink, zipped, missing_ok=True),
    )


@router.delete("/{name}", status_code=204)
async def delete_family(name: Name) -> Response:
    """Remove the saved family from this machine only (there is no unpublish)."""
    store.delete(name)
    return Response(status_code=204)
