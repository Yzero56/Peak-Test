from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.security import check_admin_password, is_logged_in, log_in, log_out
from app.templating import templates

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str | None = None):
    if is_logged_in(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login")
def login_submit(request: Request, password: str = Form(...)):
    if not check_admin_password(password):
        return RedirectResponse("/login?error=1", status_code=303)
    log_in(request)
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    log_out(request)
    return RedirectResponse("/login", status_code=303)
