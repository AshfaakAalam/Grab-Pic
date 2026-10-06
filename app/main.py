from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import BASE_DIR
from app.errors import register_exception_handlers
from app.routes import events, photos

app = FastAPI(title="Event Photo App")

# Serves /static/... (CSS later, and the locally stored uploads for now).
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(events.router)
app.include_router(photos.router)

register_exception_handlers(app)
