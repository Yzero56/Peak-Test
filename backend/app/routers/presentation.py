from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.routers.dashboard import _device_card, _fridge_online, _fridge_snapshot
from app.templating import templates

router = APIRouter(prefix="/presentation", tags=["presentation"])


@router.get("/", response_class=HTMLResponse)
def overview_presentation(request: Request, db: Session = Depends(get_db)):
    devices = [_device_card(db, d) for d in services.all_devices(db)]
    return templates.TemplateResponse(
        request,
        "dashboard/overview.html",
        {
            "device_cards": devices,
            "fridge_online": _fridge_online(),
            "read_only": True,
            "overview_partial_url": "/presentation/partials/overview",
        },
    )


@router.get("/partials/overview", response_class=HTMLResponse)
def overview_partial_presentation(request: Request, db: Session = Depends(get_db)):
    devices = [_device_card(db, d) for d in services.all_devices(db)]
    return templates.TemplateResponse(
        request,
        "dashboard/_overview_body.html",
        {"device_cards": devices, "fridge_online": _fridge_online(), "read_only": True},
    )


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
