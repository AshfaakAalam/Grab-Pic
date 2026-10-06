from fastapi.templating import Jinja2Templates

from app.core.config import BASE_DIR

templates = Jinja2Templates(directory=BASE_DIR / "templates")
