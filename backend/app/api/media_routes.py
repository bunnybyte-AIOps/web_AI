import asyncio
import json
import logging
import importlib.util
import shutil
import subprocess
import urllib.error
import urllib.request
import uuid
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, require_project_owner

router = APIRouter(prefix="/media", tags=["Media"])
logger = logging.getLogger(__name__)


class ImageGenerationRequest(BaseModel):
    project_id: int = Field(gt=0)
    scene_id: int = Field(gt=0)
    prompt: str = Field(min_length=8, max_length=4000)


class SpeechGenerationRequest(BaseModel):
    project_id: int = Field(gt=0)
    scene_id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=5000)
    voice: str = Field(default="vi-VN-HoaiMyNeural", max_length=80)


def _scene_for_user(project_id: int, scene_id: int, user_id: int) -> dict:
    require_project_owner(project_id, user_id)
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM scenes WHERE id = ? AND project_id = ?",
            (scene_id, project_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh trong dự án.")
    return dict(row)


def _create_asset(
    project_id: int,
    scene_id: int,
    name: str,
    asset_type: str,
    request_payload: dict,
) -> int:
    with get_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO assets
                (project_id, scene_id, name, asset_type, status, request_json)
            VALUES (?, ?, ?, ?, 'generating', ?)
            """,
            (
                project_id,
                scene_id,
                name,
                asset_type,
                json.dumps(request_payload, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def _set_asset_failed(asset_id: int, message: str) -> None:
    with get_db() as connection:
        connection.execute(
            """
            UPDATE assets SET status = 'failed', error_message = ?,
                updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            (message, asset_id),
        )


def _generate_image(asset_id: int, project_id: int, scene_id: int, prompt: str) -> None:
    boundary = f"cinai-{uuid.uuid4().hex}"
    fields = {
        "prompt": prompt,
        "output_format": "png",
        "aspect_ratio": "16:9",
    }
    parts = []
    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    parts.append(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        "https://api.stability.ai/v2beta/stable-image/generate/core",
        data=b"".join(parts),
        headers={
            "Authorization": f"Bearer {settings.STABILITY_API_KEY}",
            "Accept": "image/*",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            image_data = response.read()
        if not image_data:
            raise OSError("Nhà cung cấp ảnh trả về dữ liệu rỗng.")
        directory = Path(settings.STORAGE_LOCAL_DIR) / "projects" / str(project_id) / "images"
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.png"
        (directory / filename).write_bytes(image_data)
    except urllib.error.HTTPError as exc:
        _set_asset_failed(asset_id, f"Nhà cung cấp ảnh trả về HTTP {exc.code}.")
        return
    except Exception as exc:
        logger.exception("Image generation failed for asset %s", asset_id)
        _set_asset_failed(asset_id, f"Không thể tạo ảnh: {exc.__class__.__name__}.")
        return

    file_url = f"/storage/projects/{project_id}/images/{filename}"
    with get_db() as connection:
        connection.execute(
            """
            UPDATE assets SET file_url = ?, thumbnail_url = ?,
                status = 'review', error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (file_url, file_url, asset_id),
        )
        connection.execute(
            "UPDATE scenes SET image_url = ? WHERE id = ? AND project_id = ?",
            (file_url, scene_id, project_id),
        )


async def _save_speech(text: str, voice: str, output_path: Path) -> None:
    import edge_tts

    communicator = edge_tts.Communicate(text, voice)
    await communicator.save(str(output_path))


def _generate_speech(
    asset_id: int, project_id: int, scene_id: int, text: str, voice: str
) -> None:
    directory = Path(settings.STORAGE_LOCAL_DIR) / "projects" / str(project_id) / "audio"
    filename = f"{uuid.uuid4().hex}.mp3"
    output_path = directory / filename
    try:
        directory.mkdir(parents=True, exist_ok=True)
        asyncio.run(_save_speech(text, voice, output_path))
    except ImportError:
        _set_asset_failed(asset_id, "Thiếu package edge-tts; cài requirements backend.")
        return
    except Exception as exc:
        logger.exception("Speech generation failed for asset %s", asset_id)
        _set_asset_failed(asset_id, f"Không thể tạo giọng đọc: {exc.__class__.__name__}.")
        return

    file_url = f"/storage/projects/{project_id}/audio/{filename}"
    with get_db() as connection:
        connection.execute(
            """
            UPDATE assets SET file_url = ?, status = 'review', error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (file_url, asset_id),
        )
        connection.execute(
            "UPDATE scenes SET audio_url = ? WHERE id = ? AND project_id = ?",
            (file_url, scene_id, project_id),
        )


def _local_storage_file(file_url: str | None) -> Path | None:
    if not file_url or not file_url.startswith("/storage/"):
        return None
    relative = PurePosixPath(file_url).relative_to("/storage")
    root = Path(settings.STORAGE_LOCAL_DIR).resolve()
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


def _approved_scenes_for_project(
    project_id: int, episode_number: int | None = None
) -> list[dict]:
    with get_db() as connection:
        if episode_number is None:
            rows = connection.execute(
                """
                SELECT * FROM scenes
                WHERE project_id = ? AND (
                    generation_id = (
                        SELECT id FROM ai_generations
                        WHERE project_id = ? AND step = 'script'
                        ORDER BY id DESC LIMIT 1
                    )
                    OR generation_id IS NULL
                )
                ORDER BY episode_number, scene_number
                """,
                (project_id, project_id),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM scenes
                WHERE project_id = ? AND episode_number = ? AND (
                    generation_id = (
                        SELECT MAX(generation_id) FROM scenes
                        WHERE project_id = ? AND episode_number = ?
                            AND generation_id IS NOT NULL
                    )
                    OR generation_id IS NULL
                )
                ORDER BY scene_number, id
                """,
                (project_id, episode_number, project_id, episode_number),
            ).fetchall()
        scenes = [dict(row) for row in rows]
        media_assets = connection.execute(
            """
            SELECT scene_id, asset_type, file_url, status
            FROM assets WHERE project_id = ?
            """,
            (project_id,),
        ).fetchall()
    if not scenes:
        raise HTTPException(status_code=409, detail="Dự án chưa có cảnh để render.")
    approved_files = {
        (asset["scene_id"], asset["asset_type"], asset["file_url"])
        for asset in media_assets
        if asset["status"] == "approved"
    }
    if any(
        _local_storage_file(scene.get("image_url")) is None
        or _local_storage_file(scene.get("audio_url")) is None
        or (scene["id"], "visual", scene.get("image_url")) not in approved_files
        or (scene["id"], "audio", scene.get("audio_url")) not in approved_files
        for scene in scenes
    ):
        raise HTTPException(
            status_code=409,
            detail="Mỗi cảnh cần có ảnh và giọng đọc đã duyệt trước khi render.",
        )
    return scenes


def _render_video(
    render_id: int, project_id: int, scenes: list[dict], ffmpeg_path: str
) -> None:
    output_dir = Path(settings.STORAGE_LOCAL_DIR) / "projects" / str(project_id) / "renders"
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / f"job-{render_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    clips: list[str] = []
    output_path = output_dir / f"render-{render_id}.mp4"
    try:
        for index, scene in enumerate(scenes, start=1):
            image_path = _local_storage_file(scene.get("image_url"))
            audio_path = _local_storage_file(scene.get("audio_url"))
            if image_path is None or audio_path is None:
                raise ValueError("Mỗi cảnh cần có ảnh và audio trong storage.")
            duration = max(1.0, min(float(scene.get("duration") or 5), 300.0))
            clip_name = f"scene-{index:04d}.mp4"
            subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-loop",
                    "1",
                    "-framerate",
                    "24",
                    "-i",
                    str(image_path),
                    "-i",
                    str(audio_path),
                    "-t",
                    str(duration),
                    "-vf",
                    "scale=1280:720:force_original_aspect_ratio=increase,"
                    "crop=1280:720,setsar=1",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-shortest",
                    clip_name,
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                timeout=300,
            )
            clips.append(clip_name)

        concat_file = temp_dir / "clips.txt"
        concat_file.write_text(
            "".join(f"file '{clip}'\n" for clip in clips), encoding="utf-8"
        )
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                "clips.txt",
                "-c",
                "copy",
                str(output_path),
            ],
            cwd=temp_dir,
            check=True,
            capture_output=True,
            timeout=600,
        )
    except ValueError as exc:
        with get_db() as connection:
            connection.execute(
                """
                UPDATE video_renders
                SET status = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (str(exc), render_id),
            )
        return
    except (OSError, subprocess.SubprocessError) as exc:
        with get_db() as connection:
            connection.execute(
                """
                UPDATE video_renders
                SET status = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (f"FFmpeg render thất bại: {exc.__class__.__name__}.", render_id),
            )
        return

    relative = output_path.relative_to(Path(settings.STORAGE_LOCAL_DIR)).as_posix()
    file_url = f"/storage/{relative}"
    with get_db() as connection:
        connection.execute(
            """
            UPDATE video_renders
            SET status = 'ready', file_url = ?, error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (file_url, render_id),
        )
    shutil.rmtree(temp_dir, ignore_errors=True)


def _find_ffmpeg() -> str | None:
    configured = settings.FFMPEG_PATH
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = Path(__file__).resolve().parents[2] / candidate
    if candidate.is_file():
        return str(candidate.resolve())
    return shutil.which(configured)


@router.post("/images", status_code=status.HTTP_202_ACCEPTED)
def request_image(
    item: ImageGenerationRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
) -> dict:
    if not settings.STABILITY_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Cấu hình STABILITY_API_KEY ở backend để bật sinh ảnh.",
        )
    _scene_for_user(item.project_id, item.scene_id, user["id"])
    asset_id = _create_asset(
        item.project_id,
        item.scene_id,
        f"Ảnh cảnh {item.scene_id}",
        "visual",
        {"prompt": item.prompt},
    )
    background_tasks.add_task(
        _generate_image, asset_id, item.project_id, item.scene_id, item.prompt
    )
    return {"asset_id": asset_id, "status": "generating"}


@router.post("/speech", status_code=status.HTTP_202_ACCEPTED)
def request_speech(
    item: SpeechGenerationRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
) -> dict:
    _scene_for_user(item.project_id, item.scene_id, user["id"])
    asset_id = _create_asset(
        item.project_id,
        item.scene_id,
        f"Giọng đọc cảnh {item.scene_id}",
        "audio",
        {"text": item.text, "voice": item.voice},
    )
    background_tasks.add_task(
        _generate_speech,
        asset_id,
        item.project_id,
        item.scene_id,
        item.text,
        item.voice,
    )
    return {"asset_id": asset_id, "status": "generating"}


@router.get("/capabilities")
def get_media_capabilities(user: dict = Depends(get_current_user)) -> dict:
    ffmpeg_path = _find_ffmpeg()
    ffmpeg_version = None
    if ffmpeg_path:
        try:
            result = subprocess.run(
                [ffmpeg_path, "-version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            ffmpeg_version = result.stdout.splitlines()[0] if result.stdout else "available"
        except (OSError, subprocess.SubprocessError) as exc:
            ffmpeg_version = f"error: {exc.__class__.__name__}"
    return {
        "image_provider": "configured" if settings.STABILITY_API_KEY else "not_configured",
        "speech_provider": (
            "available" if importlib.util.find_spec("edge_tts") else "not_installed"
        ),
        "ffmpeg": "available" if ffmpeg_version and not ffmpeg_version.startswith("error:") else "unavailable",
        "ffmpeg_version": ffmpeg_version,
    }


@router.post("/assets/{asset_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_asset_generation(
    asset_id: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
) -> dict:
    with get_db() as connection:
        asset = connection.execute(
            "SELECT * FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
    if asset is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên.")
    require_project_owner(asset["project_id"], user["id"])
    if asset["status"] != "failed":
        raise HTTPException(
            status_code=409, detail="Chỉ có thể thử lại tài nguyên đã thất bại."
        )
    try:
        request_payload = json.loads(asset["request_json"] or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=409, detail="Không thể khôi phục thông tin yêu cầu tạo tài nguyên."
        ) from exc

    if asset["asset_type"] == "visual":
        if not settings.STABILITY_API_KEY:
            raise HTTPException(
                status_code=503,
                detail="Cấu hình STABILITY_API_KEY ở backend để bật sinh ảnh.",
            )
        prompt = request_payload.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            raise HTTPException(status_code=409, detail="Thiếu mô tả ảnh để thử lại.")
        background_tasks.add_task(
            _generate_image, asset_id, asset["project_id"], asset["scene_id"], prompt
        )
    elif asset["asset_type"] == "audio":
        text = request_payload.get("text")
        voice = request_payload.get("voice", "vi-VN-HoaiMyNeural")
        if not isinstance(text, str) or not text:
            raise HTTPException(status_code=409, detail="Thiếu lời thoại để thử lại.")
        background_tasks.add_task(
            _generate_speech,
            asset_id,
            asset["project_id"],
            asset["scene_id"],
            text,
            voice,
        )
    else:
        raise HTTPException(
            status_code=409, detail="Loại tài nguyên này chưa hỗ trợ thử lại tự động."
        )

    with get_db() as connection:
        connection.execute(
            """
            UPDATE assets SET status = 'generating', error_message = NULL,
                updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            (asset_id,),
        )
    return {"asset_id": asset_id, "status": "generating"}


@router.post("/projects/{project_id}/render", status_code=status.HTTP_202_ACCEPTED)
def request_video_render(
    project_id: int,
    background_tasks: BackgroundTasks,
    episode_number: int | None = Query(default=None, ge=1, le=1000),
    user: dict = Depends(get_current_user),
) -> dict:
    require_project_owner(project_id, user["id"])
    ffmpeg_path = _find_ffmpeg()
    if ffmpeg_path is None:
        raise HTTPException(
            status_code=503,
            detail="Không tìm thấy FFmpeg. Cài FFmpeg hoặc cấu hình FFMPEG_PATH.",
        )
    scenes = _approved_scenes_for_project(project_id, episode_number)
    with get_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO video_renders (project_id, episode_number, status)
            VALUES (?, ?, 'rendering')
            """,
            (project_id, episode_number),
        )
        render_id = int(cursor.lastrowid)
    background_tasks.add_task(
        _render_video, render_id, project_id, scenes, ffmpeg_path
    )
    return {"render_id": render_id, "status": "rendering"}


@router.get("/projects/{project_id}/renders/{render_id}")
def get_video_render(
    project_id: int,
    render_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM video_renders WHERE id = ? AND project_id = ?",
            (render_id, project_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ render.")
    return dict(row)


@router.post(
    "/projects/{project_id}/renders/{render_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_video_render(
    project_id: int,
    render_id: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
) -> dict:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        prior = connection.execute(
            "SELECT status, episode_number FROM video_renders WHERE id = ? AND project_id = ?",
            (render_id, project_id),
        ).fetchone()
    if prior is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ render.")
    if prior["status"] != "failed":
        raise HTTPException(
            status_code=409, detail="Chỉ có thể thử lại tác vụ render đã thất bại."
        )
    ffmpeg_path = _find_ffmpeg()
    if ffmpeg_path is None:
        raise HTTPException(
            status_code=503,
            detail="Không tìm thấy FFmpeg. Cài FFmpeg hoặc cấu hình FFMPEG_PATH.",
        )
    episode_number = prior["episode_number"]
    scenes = _approved_scenes_for_project(project_id, episode_number)
    with get_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO video_renders (project_id, episode_number, status)
            VALUES (?, ?, 'rendering')
            """,
            (project_id, episode_number),
        )
        new_render_id = int(cursor.lastrowid)
    background_tasks.add_task(
        _render_video, new_render_id, project_id, scenes, ffmpeg_path
    )
    return {"render_id": new_render_id, "status": "rendering"}


@router.get(
    "/projects/{project_id}/episodes/{episode_number}/subtitles.srt",
    response_class=PlainTextResponse,
)
def download_episode_subtitles(
    project_id: int,
    episode_number: int,
    user: dict = Depends(get_current_user),
) -> PlainTextResponse:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        scenes = connection.execute(
            """
            SELECT scene_number, dialogue, duration
            FROM scenes
            WHERE project_id = ? AND episode_number = ? AND (
                generation_id = (
                    SELECT MAX(generation_id) FROM scenes
                    WHERE project_id = ? AND episode_number = ?
                        AND generation_id IS NOT NULL
                )
                OR generation_id IS NULL
            )
            ORDER BY scene_number, id
            """,
            (project_id, episode_number, project_id, episode_number),
        ).fetchall()
    if not scenes:
        raise HTTPException(status_code=404, detail="Tập này chưa có phân cảnh.")

    def format_time(seconds: float) -> str:
        milliseconds = round(seconds * 1000)
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        whole_seconds, milliseconds = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"

    subtitles = []
    elapsed = 0.0
    for index, scene in enumerate(scenes, start=1):
        duration = max(1.0, min(float(scene["duration"] or 5), 300.0))
        dialogue = (scene["dialogue"] or "").strip()
        if dialogue:
            subtitles.extend(
                [
                    str(index),
                    f"{format_time(elapsed)} --> {format_time(elapsed + duration)}",
                    dialogue.replace("\r\n", "\n").replace("\r", "\n"),
                    "",
                ]
            )
        elapsed += duration
    return PlainTextResponse(
        "\n".join(subtitles),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="cinai-project-{project_id}-episode-{episode_number}.srt"'
            )
        },
    )


@router.post("/assets/{asset_id}/approve")
def approve_asset(
    asset_id: int, user: dict = Depends(get_current_user)
) -> dict[str, str]:
    with get_db() as connection:
        asset = connection.execute(
            "SELECT id, project_id, status FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
    if asset is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên.")
    require_project_owner(asset["project_id"], user["id"])
    if asset["status"] != "review":
        raise HTTPException(
            status_code=409, detail="Chỉ có thể duyệt tài nguyên đang chờ duyệt."
        )
    with get_db() as connection:
        connection.execute(
            "UPDATE assets SET status = 'approved' WHERE id = ?", (asset_id,)
        )
    return {"status": "approved", "message": "Tài nguyên đã được duyệt."}
