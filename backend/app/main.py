from pathlib import Path
import shutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import settings
from app.core.database import initialize_database
from app.core.security import decode_access_token, require_project_owner
from app.api.auth_routes import router as auth_router
from app.api.ai_routes import router as ai_router
from app.api.project_routes import router as project_router
from app.api.studio_routes import router as studio_router, dashboard_router
from app.api.media_routes import router as media_router
from app.api.social_routes import router as social_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API cho Nền tảng AI Đồng Sáng Tạo và Sản Xuất Phim Đa Phương Tiện - Đồ án 2 (VKU)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.STORAGE_LOCAL_DIR, exist_ok=True)
app.mount("/storage", StaticFiles(directory=settings.STORAGE_LOCAL_DIR), name="storage")


@app.middleware("http")
async def protect_project_storage(request: Request, call_next):
    if request.url.path.startswith("/storage/"):
        segments = request.url.path.strip("/").split("/")
        if len(segments) < 4 or segments[0] != "storage" or segments[1] != "projects":
            return JSONResponse(status_code=404, content={"detail": "Không tìm thấy tệp."})
        token = request.cookies.get("cinai_access_token")
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Cần đăng nhập."})
        try:
            payload = decode_access_token(token)
            require_project_owner(int(segments[2]), int(payload["sub"]))
        except (HTTPException, ValueError):
            return JSONResponse(status_code=404, content={"detail": "Không tìm thấy tệp."})
    return await call_next(request)


@app.on_event("startup")
def prepare_database() -> None:
    initialize_database()


app.include_router(auth_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(project_router, prefix="/api")
app.include_router(studio_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(social_router, prefix="/api")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

@app.get("/")
def get_home_page():
    index_path = PROJECT_ROOT / "index.html"
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Welcome to CINAI Platform API"}


@app.get("/index.html")
def get_index_page():
    index_path = PROJECT_ROOT / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"detail": "Không tìm thấy trang chủ."})


@app.get("/studio")
def get_studio_page():
    studio_path = PROJECT_ROOT / "studio.html"
    if studio_path.is_file():
        return FileResponse(studio_path)
    return JSONResponse(status_code=404, content={"detail": "Không tìm thấy giao diện CINAI."})


@app.get("/studio.html")
def get_studio_html():
    studio_path = PROJECT_ROOT / "studio.html"
    if studio_path.is_file():
        return FileResponse(studio_path)
    return JSONResponse(status_code=404, content={"detail": "Không tìm thấy giao diện CINAI."})


@app.get("/api/health")
def health_check():
    ffmpeg_path = Path(settings.FFMPEG_PATH)
    if not ffmpeg_path.is_absolute():
        ffmpeg_path = Path(__file__).resolve().parents[1] / ffmpeg_path
    ffmpeg_available = ffmpeg_path.is_file() or shutil.which(settings.FFMPEG_PATH) is not None
    return {
        "status": "healthy",
        "gemini_api": "configured" if settings.GEMINI_API_KEY else "not_configured",
        "grok_api": "configured" if settings.XAI_API_KEY else "not_configured",
        "database": (
            "postgresql_configured"
            if settings.DATABASE_URL.startswith(("postgresql://", "postgres://", "postgresql+"))
            else "sqlite_connected"
        ),
        "modules": {
            "authentication": "ready",
            "projects_manager": "ready",
            "ai_idea_assistant": "ready",
            "grok_provider": "ready" if settings.XAI_API_KEY else "not_configured",
            "video_renderer": "available" if ffmpeg_available else "not_configured"
        }
    }
