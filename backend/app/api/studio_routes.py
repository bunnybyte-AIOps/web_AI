import csv
import io
import json
import urllib.error
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.security import get_current_user, require_project_owner
from app.schemas.ai_schemas import AIProviderRequest
from app.services.ai_providers import get_ai_provider

router = APIRouter(tags=["Studio"])
dashboard_router = APIRouter(tags=["Dashboard"])


class AnalyticsInput(BaseModel):
    view_count: int = Field(default=0, ge=0)
    unique_viewers: int = Field(default=0, ge=0)
    watch_time_avg_sec: float = Field(default=0, ge=0)
    retention_rate: float = Field(default=0, ge=0, le=100)
    like_count: int = Field(default=0, ge=0)
    comment_count: int = Field(default=0, ge=0)
    share_count: int = Field(default=0, ge=0)


class EpisodeInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    synopsis: str = Field(default="", max_length=4000)
    season_number: int | None = Field(default=None, ge=1, le=100)



class CharacterInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="Nhân vật chính", max_length=100)
    visual_prompt: str = Field(default="", max_length=2000)
    voice_profile: str = Field(default="vi-VN-NamMinhNeural", max_length=100)
    flux_prompt: str = Field(default="", max_length=2000)


class WorldInput(BaseModel):
    name: str = Field(default="Sài Gòn Neo-2088", min_length=1, max_length=160)
    setting_description: str = Field(default="", max_length=5000)
    time_period: str = Field(default="Năm 2088", max_length=100)
    technology_level: str = Field(default="Kỷ nguyên lượng tử", max_length=100)
    factions: str = Field(default="[]")
    locations: str = Field(default="[]")
    rules: str = Field(default="[]")

class StoryInput(BaseModel):
    fountain_script: str = Field(min_length=1, max_length=100000)
    episode_number: int = Field(default=1, ge=1, le=1000)

class SceneInput(BaseModel):
    scene_number: int = Field(ge=1, le=1000)
    title: str = Field(min_length=1, max_length=200)
    visual_prompt: str = Field(default="", max_length=2000)
    dialogue: str = Field(default="", max_length=4000)
    camera_angle: str = Field(default="medium_shot", max_length=100)
    sfx: str = Field(default="", max_length=500)
    duration: float = Field(default=5.0, ge=1.0, le=300.0)
    episode_number: int = Field(default=1, ge=1, le=1000)


class SceneUpdate(BaseModel):
    scene_number: int | None = Field(default=None, ge=1, le=1000)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    visual_prompt: str | None = Field(default=None, max_length=2000)
    dialogue: str | None = Field(default=None, max_length=4000)
    camera_angle: str | None = Field(default=None, max_length=100)
    sfx: str | None = Field(default=None, max_length=500)
    duration: float | None = Field(default=None, ge=1.0, le=300.0)

class SeasonInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    synopsis: str = Field(default="", max_length=4000)


def _decode_json(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _episode_rows(connection, project_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT e.*, season.season_number, season.title AS season_title,
            (SELECT COUNT(*) FROM scenes sc
             WHERE sc.project_id = e.project_id AND sc.episode_number = e.episode_number) AS scene_count,
            (SELECT COUNT(*) FROM stories st
             WHERE st.project_id = e.project_id AND st.episode_number = e.episode_number) AS script_versions
        FROM episodes e
        LEFT JOIN seasons season ON season.id = e.season_id
        WHERE e.project_id = ?
        ORDER BY e.episode_number
        """,
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _season_rows(connection, project_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT s.*,
            (SELECT COUNT(*) FROM episodes e WHERE e.season_id = s.id) AS episode_count
        FROM seasons s
        WHERE s.project_id = ?
        ORDER BY s.season_number
        """,
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


@dashboard_router.get("/dashboard")
def get_dashboard(
    project_id: int | None = Query(default=None, gt=0),
    user: dict = Depends(get_current_user),
) -> dict:
    with get_db() as connection:
        if project_id is None:
            project = connection.execute(
                "SELECT * FROM projects WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user["id"],),
            ).fetchone()
        else:
            project = connection.execute(
                "SELECT * FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user["id"]),
            ).fetchone()
            if project is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
        totals = connection.execute(
            """
            SELECT COUNT(*) AS total_projects,
                   COALESCE(SUM(view_count), 0) AS total_views
            FROM projects WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        content = connection.execute(
            """
            SELECT COUNT(DISTINCT s.id) AS total_scenes,
                   COUNT(DISTINCT a.id) AS total_assets
            FROM projects p
            LEFT JOIN scenes s ON s.project_id = p.id
            LEFT JOIN assets a ON a.project_id = p.id
            WHERE p.user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        credits = connection.execute(
            "SELECT COUNT(*) FROM ai_generations WHERE user_id = ?",
            (user["id"],),
        ).fetchone()[0]
        pipeline = {
            "ideas": False,
            "story_bible": False,
            "script": False,
            "approved_assets": 0,
            "ready_video": False,
            "scene_count": 0,
        }
        if project is not None:
            selected_id = project["id"]
            steps = {
                row["step"]
                for row in connection.execute(
                    "SELECT DISTINCT step FROM ai_generations WHERE project_id = ?",
                    (selected_id,),
                ).fetchall()
            }
            pipeline["ideas"] = "ideas" in steps
            pipeline["story_bible"] = connection.execute(
                "SELECT 1 FROM story_bibles WHERE project_id = ? LIMIT 1",
                (selected_id,),
            ).fetchone() is not None
            pipeline["script"] = "script" in steps
            pipeline["scene_count"] = connection.execute(
                "SELECT COUNT(*) FROM scenes WHERE project_id = ?",
                (selected_id,),
            ).fetchone()[0]
            pipeline["approved_assets"] = connection.execute(
                "SELECT COUNT(*) FROM assets WHERE project_id = ? AND status = 'approved'",
                (selected_id,),
            ).fetchone()[0]
            pipeline["ready_video"] = connection.execute(
                "SELECT 1 FROM video_renders WHERE project_id = ? AND status = 'ready' LIMIT 1",
                (selected_id,),
            ).fetchone() is not None
    return {
        "project": dict(project) if project else None,
        "total_projects": totals["total_projects"],
        "total_scenes": content["total_scenes"],
        "total_assets": content["total_assets"],
        "total_views": totals["total_views"],
        "ai_credits_used": credits,
        "pipeline": pipeline,
    }


@dashboard_router.get("/users/stats/overview")
def get_user_stats(user: dict = Depends(get_current_user)) -> dict:
    data = get_dashboard(user)
    return {
        "total_projects": data["total_projects"],
        "total_scenes": data["total_scenes"],
        "total_assets": data["total_assets"],
        "total_views": data["total_views"],
        "ai_credits_used": data["ai_credits_used"],
    }


@router.get("/projects/{project_id}/story")
def get_project_story(
    project_id: int,
    episode_number: int | None = Query(default=None, ge=1, le=1000),
    user: dict = Depends(get_current_user),
) -> dict:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        bible = connection.execute(
            """
            SELECT * FROM story_bibles WHERE project_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        if episode_number is None:
            story = connection.execute(
                "SELECT * FROM stories WHERE project_id = ? ORDER BY id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            scenes = connection.execute(
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
            story = connection.execute(
                """
                SELECT * FROM stories
                WHERE project_id = ? AND episode_number = ?
                ORDER BY id DESC LIMIT 1
                """,
                (project_id, episode_number),
            ).fetchone()
            scenes = connection.execute(
                """
                SELECT * FROM scenes
                WHERE project_id = ? AND episode_number = ? AND (
                    generation_id = (
                        SELECT id FROM ai_generations
                        WHERE id = (
                            SELECT generation_id FROM scenes
                            WHERE project_id = ? AND episode_number = ?
                                AND generation_id IS NOT NULL
                            ORDER BY generation_id DESC LIMIT 1
                        )
                        ORDER BY id DESC LIMIT 1
                    )
                    OR generation_id IS NULL
                )
                ORDER BY scene_number, id
                """,
                (project_id, episode_number, project_id, episode_number),
            ).fetchall()
    bible_data = _decode_json(bible["data_json"], {}) if bible else {}
    story_data = _decode_json(story["data_json"], {}) if story else {}
    return {
        **bible_data,
        **story_data,
        "logline": (bible["logline"] if bible else None) or bible_data.get("logline"),
        "story_bible": bible_data,
        "fountain_script": (
            story["fountain_script"] if story else None
        ) or story_data.get("fountain_script") or story_data.get("script"),
        "scenes": [dict(row) for row in scenes],
    }


@router.get("/projects/{project_id}/episodes")
def list_project_episodes(
    project_id: int, user: dict = Depends(get_current_user)
) -> list[dict[str, Any]]:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        return _episode_rows(connection, project_id)


@router.get("/projects/{project_id}/seasons")
def list_project_seasons(
    project_id: int, user: dict = Depends(get_current_user)
) -> list[dict[str, Any]]:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        return _season_rows(connection, project_id)


@router.post("/projects/{project_id}/seasons", status_code=201)
def create_project_season(
    project_id: int,
    item: SeasonInput,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    require_project_owner(project_id, user["id"])
    title = item.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Tên mùa không được để trống.")
    with get_db() as connection:
        season_number = connection.execute(
            "SELECT COALESCE(MAX(season_number), 0) + 1 FROM seasons WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        cursor = connection.execute(
            """
            INSERT INTO seasons (project_id, season_number, title, synopsis)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, season_number, title, item.synopsis.strip()),
        )
        season = connection.execute(
            "SELECT * FROM seasons WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(season)


@router.put("/projects/{project_id}/seasons/{season_number}")
def update_project_season(
    project_id: int,
    season_number: int,
    item: SeasonInput,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    require_project_owner(project_id, user["id"])
    title = item.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Tên mùa không được để trống.")
    with get_db() as connection:
        cursor = connection.execute(
            """
            UPDATE seasons SET title = ?, synopsis = ?, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = ? AND season_number = ?
            """,
            (title, item.synopsis.strip(), project_id, season_number),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy mùa.")
        season = connection.execute(
            """
            SELECT * FROM seasons
            WHERE project_id = ? AND season_number = ?
            """,
            (project_id, season_number),
        ).fetchone()
    return dict(season)


@router.delete("/projects/{project_id}/seasons/{season_number}")
def delete_project_season(
    project_id: int,
    season_number: int,
    user: dict = Depends(get_current_user),
) -> dict[str, str]:
    require_project_owner(project_id, user["id"])
    if season_number == 1:
        raise HTTPException(status_code=409, detail="Không thể xóa mùa đầu tiên của dự án.")
    with get_db() as connection:
        season = connection.execute(
            """
            SELECT id FROM seasons
            WHERE project_id = ? AND season_number = ?
            """,
            (project_id, season_number),
        ).fetchone()
        if season is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy mùa.")
        episode_count = connection.execute(
            "SELECT COUNT(*) FROM episodes WHERE season_id = ?",
            (season["id"],),
        ).fetchone()[0]
        if episode_count:
            raise HTTPException(
                status_code=409,
                detail="Không thể xóa mùa đang có tập. Hãy chuyển hoặc xóa các tập trước.",
            )
        connection.execute("DELETE FROM seasons WHERE id = ?", (season["id"],))
    return {"message": "Đã xóa mùa."}


@router.post("/projects/{project_id}/episodes", status_code=201)
def create_project_episode(
    project_id: int,
    item: EpisodeInput,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    require_project_owner(project_id, user["id"])
    title = item.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Tên tập không được để trống.")
    with get_db() as connection:
        season_number = item.season_number or 1
        season = connection.execute(
            """
            SELECT id FROM seasons
            WHERE project_id = ? AND season_number = ?
            """,
            (project_id, season_number),
        ).fetchone()
        if season is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy mùa đã chọn.")
        episode_number = connection.execute(
            "SELECT COALESCE(MAX(episode_number), 0) + 1 FROM episodes WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        cursor = connection.execute(
            """
            INSERT INTO episodes
                (project_id, season_id, episode_number, title, synopsis)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                season["id"],
                episode_number,
                title,
                item.synopsis.strip(),
            ),
        )
        row = connection.execute(
            "SELECT * FROM episodes WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


@router.put("/projects/{project_id}/episodes/{episode_number}")
def update_project_episode(
    project_id: int,
    episode_number: int,
    item: EpisodeInput,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    require_project_owner(project_id, user["id"])
    title = item.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Tên tập không được để trống.")
    with get_db() as connection:
        values = [title, item.synopsis.strip()]
        season_clause = ""
        if item.season_number is not None:
            season = connection.execute(
                """
                SELECT id FROM seasons
                WHERE project_id = ? AND season_number = ?
                """,
                (project_id, item.season_number),
            ).fetchone()
            if season is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy mùa đã chọn.")
            season_clause = ", season_id = ?"
            values.append(season["id"])
        cursor = connection.execute(
            f"""
            UPDATE episodes
            SET title = ?, synopsis = ?{season_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = ? AND episode_number = ?
            """,
            (*values, project_id, episode_number),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy tập.")
        row = connection.execute(
            """
            SELECT * FROM episodes
            WHERE project_id = ? AND episode_number = ?
            """,
            (project_id, episode_number),
        ).fetchone()
    return dict(row)


@router.get("/projects/{project_id}/generations")
def get_project_generations(
    project_id: int,
    limit: int = Query(default=20, ge=1, le=50),
    step: str | None = Query(default=None, max_length=50),
    user: dict = Depends(get_current_user),
) -> list[dict]:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        if step:
            rows = connection.execute(
                """
                SELECT id, step, input_json, output_json, status, created_at
                FROM ai_generations
                WHERE project_id = ? AND user_id = ? AND step = ?
                ORDER BY id DESC LIMIT ?
                """,
                (project_id, user["id"], step, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, step, input_json, output_json, status, created_at
                FROM ai_generations
                WHERE project_id = ? AND user_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (project_id, user["id"], limit),
            ).fetchall()
    return [
        {
            **dict(row),
            "input": _decode_json(row["input_json"], {}),
            "output": _decode_json(row["output_json"], {}),
        }
        for row in rows
    ]


@router.post("/projects/{project_id}/generations/{generation_id}/restore")
def restore_project_generation(
    project_id: int,
    generation_id: int,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        generation = connection.execute(
            """
            SELECT * FROM ai_generations
            WHERE id = ? AND project_id = ? AND user_id = ?
            """,
            (generation_id, project_id, user["id"]),
        ).fetchone()
        if generation is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản AI.")
        output = _decode_json(generation["output_json"], None)
        if not isinstance(output, dict):
            raise HTTPException(status_code=409, detail="Dữ liệu phiên bản không hợp lệ.")

        if generation["step"] == "story_bible":
            world = output.get("world_bible", {})
            characters = output.get("character_bible", [])
            if not isinstance(world, dict) or not isinstance(characters, list):
                raise HTTPException(status_code=409, detail="Story Bible của phiên bản bị lỗi.")
            connection.execute(
                """
                INSERT INTO story_bibles
                    (project_id, logline, theme, world_setting, character_profiles, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    output.get("logline"),
                    output.get("theme"),
                    json.dumps(world, ensure_ascii=False),
                    json.dumps(characters, ensure_ascii=False),
                    json.dumps(output, ensure_ascii=False),
                ),
            )
            world_name = world.get("world_name") or world.get("name")
            if world_name:
                world_values = (
                    world.get("era_setting") or world.get("setting_description"),
                    world.get("time_period"),
                    json.dumps(world.get("factions", []), ensure_ascii=False),
                    json.dumps(world.get("locations", []), ensure_ascii=False),
                    json.dumps(
                        world.get("rules_and_lore", world.get("rules", [])),
                        ensure_ascii=False,
                    ),
                )
                existing_world = connection.execute(
                    "SELECT id FROM worlds WHERE project_id = ? AND name = ?",
                    (project_id, str(world_name)[:200]),
                ).fetchone()
                if existing_world:
                    connection.execute(
                        """
                        UPDATE worlds
                        SET setting_description = ?, time_period = ?,
                            factions = ?, locations = ?, rules = ?
                        WHERE id = ?
                        """,
                        (*world_values, existing_world["id"]),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO worlds
                            (project_id, name, setting_description, time_period,
                             factions, locations, rules)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            project_id,
                            str(world_name)[:200],
                            *world_values,
                        ),
                    )
            for character in characters:
                if not isinstance(character, dict) or not character.get("name"):
                    continue
                character_name = str(character["name"])[:200]
                character_values = (
                    character.get("role") or character.get("role_type"),
                    character.get("voice_profile"),
                    character.get("visual_prompt"),
                    character.get("personality"),
                    character.get("backstory"),
                    character.get("flux_prompt") or character.get("visual_prompt"),
                    character.get("voice_id") or character.get("edge_tts_voice"),
                )
                existing_character = connection.execute(
                    "SELECT id FROM characters WHERE project_id = ? AND name = ?",
                    (project_id, character_name),
                ).fetchone()
                if existing_character:
                    connection.execute(
                        """
                        UPDATE characters
                        SET role_type = ?, voice_profile = ?, visual_prompt = ?,
                            personality = ?, backstory = ?, flux_prompt = ?,
                            edge_tts_voice = ?
                        WHERE id = ?
                        """,
                        (*character_values, existing_character["id"]),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO characters
                            (project_id, name, role_type, voice_profile, visual_prompt,
                             personality, backstory, flux_prompt, edge_tts_voice)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (project_id, character_name, *character_values),
                    )
        elif generation["step"] == "script":
            scenes = output.get("scenes")
            if not isinstance(scenes, list) or not scenes:
                raise HTTPException(status_code=409, detail="Phiên bản không có phân cảnh để khôi phục.")
            inputs = _decode_json(generation["input_json"], {})
            episode_number = inputs.get("episode_number", 1) if isinstance(inputs, dict) else 1
            episode_number = max(1, min(int(episode_number or 1), 1000))
            script_text = output.get("fountain_script") or output.get("script")
            cursor = connection.execute(
                """
                INSERT INTO ai_generations
                    (user_id, project_id, step, input_json, output_json, status)
                VALUES (?, ?, ?, ?, ?, 'restored')
                """,
                (
                    user["id"],
                    project_id,
                    generation["step"],
                    generation["input_json"],
                    generation["output_json"],
                ),
            )
            restored_generation_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO stories
                    (project_id, episode_number, generation_id, fountain_script, data_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    episode_number,
                    restored_generation_id,
                    script_text,
                    json.dumps(output, ensure_ascii=False),
                ),
            )
            for index, scene in enumerate(scenes, start=1):
                if not isinstance(scene, dict):
                    continue
                connection.execute(
                    """
                    INSERT INTO scenes
                        (project_id, episode_number, generation_id, scene_number, title,
                         visual_prompt, dialogue, camera_angle, sfx, duration, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')
                    """,
                    (
                        project_id,
                        episode_number,
                        restored_generation_id,
                        int(scene.get("scene_number", index)),
                        scene.get("scene_title") or scene.get("title"),
                        scene.get("visual_prompt_en") or scene.get("visual_prompt"),
                        scene.get("dialogue_vi") or scene.get("dialogue"),
                        scene.get("camera_angle"),
                        json.dumps(scene.get("sound_fx"), ensure_ascii=False)
                        if scene.get("sound_fx") is not None
                        else None,
                        float(scene.get("estimated_duration") or scene.get("duration") or 5),
                    ),
                )
            connection.execute(
                """
                INSERT INTO ai_generations
                    (user_id, project_id, step, input_json, output_json, status)
                VALUES (?, ?, 'script_restore', ?, ?, 'completed')
                """,
                (
                    user["id"],
                    project_id,
                    json.dumps({"source_generation_id": generation_id}, ensure_ascii=False),
                    json.dumps({"restored_generation_id": restored_generation_id}, ensure_ascii=False),
                ),
            )
        elif generation["step"] == "analytics_recommendations":
            recommendations = output.get("recommendations", [])
            if not isinstance(recommendations, list):
                raise HTTPException(status_code=409, detail="Phiên bản gợi ý không hợp lệ.")
            connection.execute(
                "DELETE FROM ai_recommendations WHERE project_id = ?", (project_id,)
            )
            for recommendation in recommendations:
                if isinstance(recommendation, dict) and recommendation.get("title") and recommendation.get("description"):
                    connection.execute(
                        """
                        INSERT INTO ai_recommendations (project_id, title, description, data_json)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            project_id,
                            str(recommendation["title"]),
                            str(recommendation["description"]),
                            json.dumps(recommendation, ensure_ascii=False),
                        ),
                    )
        elif generation["step"] != "ideas":
            raise HTTPException(
                status_code=409,
                detail="Bước AI này chưa hỗ trợ khôi phục trực tiếp.",
            )
    generation_input = _decode_json(generation["input_json"], {})
    return {
        "status": "restored",
        "step": generation["step"],
        "output": output,
        "episode_number": (
            generation_input.get("episode_number")
            if isinstance(generation_input, dict)
            else None
        ),
    }


@router.get("/projects/{project_id}/analytics")
def get_project_analytics(
    project_id: int, user: dict = Depends(get_current_user)
) -> dict:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        latest = connection.execute(
            """
            SELECT * FROM analytics WHERE project_id = ?
            ORDER BY recorded_at DESC, id DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        history = connection.execute(
            """
            SELECT * FROM analytics WHERE project_id = ?
            ORDER BY recorded_at DESC, id DESC LIMIT 30
            """,
            (project_id,),
        ).fetchall()
        recommendations = connection.execute(
            """
            SELECT * FROM ai_recommendations WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
    return {
        "status": "ok",
        "data": {
            "latest": dict(latest) if latest else None,
            "history": [dict(row) for row in history],
            "ai_recommendations": [
                {**dict(row), "data_json": _decode_json(row["data_json"], {})}
                for row in recommendations
            ],
            "total_recommendations": len(recommendations),
        },
    }


@router.post("/projects/{project_id}/analytics", status_code=201)
def record_project_analytics(
    project_id: int,
    item: AnalyticsInput,
    user: dict = Depends(get_current_user),
) -> dict:
    require_project_owner(project_id, user["id"])
    values = item.model_dump()
    with get_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO analytics
                (project_id, view_count, unique_viewers, watch_time_avg_sec,
                 retention_rate, like_count, comment_count, share_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                values["view_count"],
                values["unique_viewers"],
                values["watch_time_avg_sec"],
                values["retention_rate"],
                values["like_count"],
                values["comment_count"],
                values["share_count"],
            ),
        )
        connection.execute(
            "UPDATE projects SET view_count = ? WHERE id = ?",
            (values["view_count"], project_id),
        )
        row = connection.execute(
            "SELECT * FROM analytics WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return {"status": "ok", "data": dict(row)}


@router.post("/projects/{project_id}/analytics/import-csv")
async def import_project_analytics_csv(
    project_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    require_project_owner(project_id, user["id"])
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Vui lòng chọn tệp .csv.")
    content = await file.read(2_000_001)
    if len(content) > 2_000_000:
        raise HTTPException(status_code=413, detail="Tệp CSV không được vượt quá 2 MB.")
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        required_fields = set(AnalyticsInput.model_fields)
        if reader.fieldnames is None or not required_fields.issubset(reader.fieldnames):
            raise HTTPException(
                status_code=422,
                detail=(
                    "CSV cần có các cột: "
                    + ", ".join(sorted(required_fields))
                    + ". Có thể bỏ qua cột id, project_id, recorded_at."
                ),
            )
        rows = list(reader)
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422, detail="Tệp CSV phải được mã hóa UTF-8."
        ) from exc
    if not rows:
        raise HTTPException(status_code=422, detail="CSV không có dòng dữ liệu.")
    if len(rows) > 500:
        raise HTTPException(status_code=413, detail="Mỗi lần chỉ nhập tối đa 500 dòng.")

    parsed_rows = []
    for line_number, row in enumerate(rows, start=2):
        try:
            values = AnalyticsInput.model_validate(row).model_dump()
            recorded_at = (row.get("recorded_at") or "").strip()
            if recorded_at:
                datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
            parsed_rows.append((values, recorded_at))
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Dòng {line_number} có số liệu không hợp lệ: {exc}",
            ) from exc
        except Exception as exc:
            if hasattr(exc, "errors"):
                raise HTTPException(
                    status_code=422,
                    detail=f"Dòng {line_number} có trường không hợp lệ.",
                ) from exc
            raise

    with get_db() as connection:
        for values, recorded_at in parsed_rows:
            columns = (
                "project_id, view_count, unique_viewers, watch_time_avg_sec, "
                "retention_rate, like_count, comment_count, share_count"
            )
            placeholders = "?, ?, ?, ?, ?, ?, ?, ?"
            params = [
                project_id,
                values["view_count"],
                values["unique_viewers"],
                values["watch_time_avg_sec"],
                values["retention_rate"],
                values["like_count"],
                values["comment_count"],
                values["share_count"],
            ]
            if recorded_at:
                columns += ", recorded_at"
                placeholders += ", ?"
                params.append(recorded_at)
            connection.execute(
                f"INSERT INTO analytics ({columns}) VALUES ({placeholders})",
                params,
            )
        latest = max(
            (entry for entry in parsed_rows if entry[1]),
            key=lambda entry: entry[1],
            default=parsed_rows[-1],
        )[0]
        connection.execute(
            "UPDATE projects SET view_count = ? WHERE id = ?",
            (latest["view_count"], project_id),
        )
    return {"status": "ok", "imported": len(parsed_rows)}


@router.post("/projects/{project_id}/recommendations")
def create_project_recommendations(
    project_id: int,
    item: AIProviderRequest = Body(default=AIProviderRequest()),
    user: dict = Depends(get_current_user),
) -> dict:
    require_project_owner(project_id, user["id"])
    provider = get_ai_provider(item.ai_provider)
    with get_db() as connection:
        project = connection.execute(
            "SELECT id, title, description, genre FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        analytics = connection.execute(
            """
            SELECT * FROM analytics WHERE project_id = ?
            ORDER BY recorded_at DESC, id DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        story = connection.execute(
            "SELECT data_json FROM story_bibles WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    if analytics is None:
        raise HTTPException(
            status_code=409, detail="Hãy lưu số liệu analytics trước khi yêu cầu gợi ý."
        )
    inputs = {
        "project": dict(project),
        "story_bible": _decode_json(story["data_json"], {}) if story else {},
        "analytics": dict(analytics),
        "ai_provider": item.ai_provider,
    }
    try:
        result = provider.generate_analytics_recommendations(
            inputs["project"], inputs["analytics"]
        )
    except (RuntimeError, json.JSONDecodeError, urllib.error.URLError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Lỗi từ {item.ai_provider}: {exc}"
        ) from exc
    recommendations = result.get("recommendations")
    if not isinstance(recommendations, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("title"), str)
        and isinstance(item.get("description"), str)
        for item in recommendations
    ):
        raise HTTPException(
            status_code=502,
            detail=f"{item.ai_provider} trả về danh sách gợi ý không hợp lệ.",
        )
    with get_db() as connection:
        connection.execute("DELETE FROM ai_recommendations WHERE project_id = ?", (project_id,))
        for item in recommendations:
            connection.execute(
                """
                INSERT INTO ai_recommendations (project_id, title, description, data_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    project_id,
                    item["title"],
                    item["description"],
                    json.dumps(item, ensure_ascii=False),
                ),
            )
        connection.execute(
            """
            INSERT INTO ai_generations
                (user_id, project_id, step, input_json, output_json)
            VALUES (?, ?, 'analytics_recommendations', ?, ?)
            """,
            (
                user["id"],
                project_id,
                json.dumps(inputs, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
            ),
        )
    return result



@router.post("/projects/{project_id}/characters", status_code=201)
def create_project_character(
    project_id: int, payload: CharacterInput, user: dict = Depends(get_current_user)
) -> dict:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO characters (project_id, name, role_type, visual_prompt, voice_profile, flux_prompt, edge_tts_voice, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'APPROVED')
            """,
            (project_id, payload.name, payload.role, payload.visual_prompt, payload.voice_profile, payload.flux_prompt or payload.visual_prompt, payload.voice_profile),
        )
        new_id = cursor.lastrowid
        row = connection.execute("SELECT * FROM characters WHERE id = ?", (new_id,)).fetchone()
    return {
        **dict(row),
        "role": row["role_type"],
        "voice_profile": row["voice_profile"] or row["edge_tts_voice"],
    }

@router.delete("/projects/{project_id}/characters/{char_id}")
def delete_project_character(
    project_id: int, char_id: int, user: dict = Depends(get_current_user)
) -> dict:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        connection.execute("DELETE FROM characters WHERE id = ? AND project_id = ?", (char_id, project_id))
    return {"message": "Đã xóa nhân vật thành công"}

@router.post("/projects/{project_id}/scenes", status_code=201)
def create_project_scene(
    project_id: int, payload: SceneInput, user: dict = Depends(get_current_user)
) -> dict:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO scenes (project_id, scene_number, title, visual_prompt, dialogue, camera_angle, sfx, duration, status, episode_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'APPROVED', ?)
            """,
            (
                project_id,
                payload.scene_number,
                payload.title,
                payload.visual_prompt,
                payload.dialogue,
                payload.camera_angle,
                payload.sfx,
                payload.duration,
                payload.episode_number,
            ),
        )
        new_id = cursor.lastrowid
        row = connection.execute("SELECT * FROM scenes WHERE id = ?", (new_id,)).fetchone()
    return dict(row)


@router.put("/projects/{project_id}/scenes/{scene_id}")
def update_project_scene(
    project_id: int,
    scene_id: int,
    payload: SceneUpdate,
    user: dict = Depends(get_current_user),
) -> dict:
    require_project_owner(project_id, user["id"])
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Không có trường nào để cập nhật.")
    set_clause = ", ".join(f"{field} = ?" for field in updates)
    with get_db() as connection:
        result = connection.execute(
            f"UPDATE scenes SET {set_clause} WHERE id = ? AND project_id = ?",
            (*updates.values(), scene_id, project_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy phân cảnh.")
        row = connection.execute(
            "SELECT * FROM scenes WHERE id = ? AND project_id = ?",
            (scene_id, project_id),
        ).fetchone()
    return dict(row)


@router.delete("/projects/{project_id}/scenes/{scene_id}")
def delete_project_scene(
    project_id: int, scene_id: int, user: dict = Depends(get_current_user)
) -> dict:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        connection.execute("DELETE FROM scenes WHERE id = ? AND project_id = ?", (scene_id, project_id))
    return {"message": "Đã xóa phân cảnh thành công"}

@router.get("/projects/{project_id}/characters")
def get_project_characters(
    project_id: int, user: dict = Depends(get_current_user)
) -> list[dict]:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        rows = connection.execute(
            "SELECT * FROM characters WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall()
    return [
        {
            **dict(row),
            "role": row["role_type"],
            "voice_profile": row["voice_profile"] or row["edge_tts_voice"],
        }
        for row in rows
    ]



@router.post("/projects/{project_id}/worlds", status_code=201)
def update_or_create_project_world(
    project_id: int, payload: WorldInput, user: dict = Depends(get_current_user)
) -> dict:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        existing = connection.execute(
            "SELECT id FROM worlds WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE worlds
                SET name = ?, setting_description = ?, factions = ?, locations = ?, rules = ?
                WHERE id = ?
                """,
                (payload.name, payload.setting_description, payload.factions, payload.locations, payload.rules, existing["id"]),
            )
            wid = existing["id"]
        else:
            cur = connection.execute(
                """
                INSERT INTO worlds (project_id, name, setting_description, time_period, technology_level, factions, locations, rules)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, payload.name, payload.setting_description, payload.time_period, payload.technology_level, payload.factions, payload.locations, payload.rules),
            )
            wid = cur.lastrowid
        row = connection.execute("SELECT * FROM worlds WHERE id = ?", (wid,)).fetchone()
    world = dict(row)
    for field in ("factions", "locations", "rules"):
        world[field] = _decode_json(world[field], [])
    return world

@router.put("/projects/{project_id}/story")
def save_project_story(
    project_id: int, payload: StoryInput, user: dict = Depends(get_current_user)
) -> dict:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        existing = connection.execute(
            "SELECT id FROM stories WHERE project_id = ? AND episode_number = ?",
            (project_id, payload.episode_number),
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE stories SET fountain_script = ? WHERE id = ?",
                (payload.fountain_script, existing["id"]),
            )
        else:
            connection.execute(
                "INSERT INTO stories (project_id, episode_number, fountain_script) VALUES (?, ?, ?)",
                (project_id, payload.episode_number, payload.fountain_script),
            )
    return {"message": "Đã lưu kịch bản thành công!"}

@router.get("/projects/{project_id}/worlds")
def get_project_world(
    project_id: int, user: dict = Depends(get_current_user)
) -> dict | None:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM worlds WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    if row is None:
        return None
    world = dict(row)
    for field in ("factions", "locations", "rules"):
        world[field] = _decode_json(world[field], [])
    return world


@router.get("/projects/{project_id}/scenes")
def get_project_scenes(
    project_id: int,
    episode_number: int | None = Query(default=None, ge=1, le=1000),
    user: dict = Depends(get_current_user),
) -> list[dict]:
    require_project_owner(project_id, user["id"])
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
    result = []
    for row in rows:
        scene = dict(row)
        scene["dialogue"] = _decode_json(scene["dialogue"], scene["dialogue"])
        scene["sfx"] = _decode_json(scene["sfx"], scene["sfx"])
        result.append(scene)
    return result


@router.get("/projects/{project_id}/assets")
def get_project_assets(
    project_id: int, user: dict = Depends(get_current_user)
) -> list[dict]:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        rows = connection.execute(
            "SELECT * FROM assets WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return [
        {**dict(row), "tags": _decode_json(row["tags"], row["tags"])}
        for row in rows
    ]
