from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.routers.dashboard import _fridge_snapshot
from app.templating import templates

router = APIRouter(prefix="/presentation", tags=["presentation"])


@router.get("/fridge", response_class=HTMLResponse)
def fridge_presentation(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard/fridge.html",
        {**_fridge_snapshot(), "read_only": True, "fridge_partial_url": "/presentation/partials/fridge"},
    )


@router.get("/partials/fridge", response_class=HTMLResponse)
def fridge_partial_presentation(request: Request):
    return templates.TemplateResponse(
        request, "dashboard/_fridge_body.html", {**_fridge_snapshot(), "read_only": True}
    )
