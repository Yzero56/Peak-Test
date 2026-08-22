from fastapi.templating import Jinja2Templates

from app.config import BACKEND_DIR

templates = Jinja2Templates(directory=str(BACKEND_DIR / "app" / "templates"))
