"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .database import Base, SessionLocal, engine
from .models import User, UserSetting
from .routers import admin, auth, news, predictions, users
from .security import hash_password, validate_password_strength
from .services import app_settings
from .services.logging_service import log_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def seed_admin() -> None:
    """Create the first administrator from ADMIN_EMAIL / ADMIN_PASSWORD if none exists."""
    if not (settings.admin_email and settings.admin_password):
        return
    db = SessionLocal()
    try:
        if db.query(User).filter(User.role == "Administrator").count():
            return
        err = validate_password_strength(settings.admin_password)
        if err:
            log.error("ADMIN_PASSWORD rejected: %s", err); return
        u = User(first_name="System", last_name="Administrator", email=settings.admin_email.lower(),
                 password=hash_password(settings.admin_password), role="Administrator")
        u.settings = UserSetting()
        db.add(u); db.commit()
        log.info("Created initial administrator %s", u.email)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    seed_admin()
    yield


app = FastAPI(title="Fake News Explainability Platform", version="1.0.0", lifespan=lifespan,
              description="Decision-support API: classifies news as Fake/Real and explains why (LIME/SHAP).")

app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Turn pydantic errors into short messages that can be shown directly to users."""
    errors, msgs = [], []
    for e in exc.errors():
        field = ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path"))
        if "email" in field.lower():
            msg = "Invalid email format"
        elif e["type"] == "missing":
            msg = f"{field} is required"
        else:
            msg = f"{field}: {e['msg'].replace('Value error, ', '')}" if field else e["msg"]
        msgs.append(msg)
        errors.append({"field": field, "message": msg})
    return JSONResponse(status_code=422, content={"detail": "; ".join(dict.fromkeys(msgs)), "errors": errors})


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and not request.url.path.startswith("/api"):
        return JSONResponse(status_code=404, content={"detail": "Page not found"})
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    db = SessionLocal()
    try:
        log_event(db, "Error", f"{request.method} {request.url.path}: {type(exc).__name__}: {exc}", None, request)
    finally:
        db.close()
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. The error has been logged."})


for r in (auth.router, users.router, news.router, predictions.router, admin.router):
    app.include_router(r)

app.mount("/media/avatars", StaticFiles(directory=Path(settings.storage_dir) / "avatars"), name="avatars")


@app.get("/api/settings/public", tags=["system"])
def public_settings():
    """Non-sensitive settings the login page needs before anybody is authenticated."""
    db = SessionLocal()
    try:
        return {"default_theme": app_settings.get(db, "theme")}
    finally:
        db.close()


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}
