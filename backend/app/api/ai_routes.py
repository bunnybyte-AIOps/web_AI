import json
import urllib.error

from fastapi import APIRouter, Depends, HTTPException
from app.schemas.ai_schemas import IdeaRequest, ConceptChoiceRequest, ScriptGenerationRequest
from app.services.ai_providers import get_ai_provider
from app.core.database import get_db
from app.core.security import get_current_user, require_project_owner

router = APIRouter(prefix="/ai", tags=["AI Orchestration"])


def _decode_json(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


@router.post("/ideas/generate")
def generate_concepts(req: IdeaRequest, user: dict = Depends(get_current_user)):
    """
    AI Idea Assistant: Nhập ý tưởng thô -> AI đề xuất 3-5 concepts cùng các câu hỏi khai thác bối cảnh.
    """
    require_project_owner(req.project_id, user["id"])
    provider = get_ai_provider(req.ai_provider)
    try:
        result = provider.generate_concepts(req.raw_idea, req.genre)
    except (RuntimeError, json.JSONDecodeError, urllib.error.URLError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Lỗi từ {req.ai_provider}: {exc}"
        ) from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Gemini trả về dữ liệu không hợp lệ.")
    if not isinstance(result.get("concepts"), list) or not all(
        isinstance(concept, dict) for concept in result["concepts"]
    ):
        raise HTTPException(
            status_code=502, detail="Gemini trả về danh sách concept không hợp lệ."
        )
    _save_generation(req.project_id, user["id"], "ideas", req.model_dump(), result)
    return result

@router.post("/story-bible/generate")
def generate_story_bible(req: ConceptChoiceRequest, user: dict = Depends(get_current_user)):
    """
    Tạo Story Bible: Thiết lập Character Memory & World Memory nhất quán giữa các tập.
    """
    require_project_owner(req.project_id, user["id"])
    provider = get_ai_provider(req.ai_provider)
    try:
        result = provider.generate_story_bible(
            req.selected_concept, req.creator_answers
        )
    except (RuntimeError, json.JSONDecodeError, urllib.error.URLError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Lỗi từ {req.ai_provider}: {exc}"
        ) from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Gemini trả về dữ liệu không hợp lệ.")
    if not isinstance(result.get("world_bible", {}), dict) or not isinstance(
        result.get("character_bible", []), list
    ):
        raise HTTPException(status_code=502, detail="Gemini trả về Story Bible không hợp lệ.")
    data_json = json.dumps(result, ensure_ascii=False)
    with get_db() as connection:
        connection.execute(
            """
            INSERT INTO story_bibles
                (project_id, logline, theme, world_setting, character_profiles, data_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                req.project_id,
                result.get("logline"),
                result.get("theme"),
                json.dumps(result.get("world_bible", {}), ensure_ascii=False),
                json.dumps(result.get("character_bible", []), ensure_ascii=False),
                data_json,
            ),
        )
        world = result.get("world_bible", {})
        world_name = world.get("world_name") or world.get("name")
        if world_name:
            existing_world = connection.execute(
                "SELECT id FROM worlds WHERE project_id = ? AND name = ?",
                (req.project_id, world_name),
            ).fetchone()
            if existing_world is None:
                connection.execute(
                    """
                    INSERT INTO worlds
                        (project_id, name, setting_description, time_period,
                         factions, locations, rules)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        req.project_id,
                        world_name,
                        world.get("era_setting") or world.get("setting_description"),
                        world.get("time_period"),
                        json.dumps(world.get("factions", []), ensure_ascii=False),
                        json.dumps(world.get("locations", []), ensure_ascii=False),
                        json.dumps(
                            world.get("rules_and_lore", world.get("rules", [])),
                            ensure_ascii=False,
                        ),
                    ),
                )
        for character in result.get("character_bible", []):
            if not isinstance(character, dict) or not character.get("name"):
                continue
            exists = connection.execute(
                "SELECT id FROM characters WHERE project_id = ? AND name = ?",
                (req.project_id, character["name"]),
            ).fetchone()
            if exists is None:
                connection.execute(
                    """
                    INSERT INTO characters
                        (project_id, name, role_type, voice_profile, visual_prompt,
                         personality, backstory, flux_prompt, edge_tts_voice)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        req.project_id,
                        character["name"],
                        character.get("role") or character.get("role_type"),
                        character.get("voice_profile"),
                        character.get("visual_prompt"),
                        character.get("personality"),
                        character.get("backstory"),
                        character.get("flux_prompt") or character.get("visual_prompt"),
                        character.get("voice_id") or character.get("edge_tts_voice"),
                    ),
                )
        _insert_generation(
            connection, req.project_id, user["id"], "story_bible",
            req.model_dump(), result
        )
    return result

@router.post("/scripts/generate")
def generate_script_scenes(req: ScriptGenerationRequest, user: dict = Depends(get_current_user)):
    """
    Sinh Kịch bản & Phân cảnh (Scene Breakdown): visual prompts cho ảnh, lời thoại cho voice TTS.
    """
    require_project_owner(req.project_id, user["id"])
    provider = get_ai_provider(req.ai_provider)
    episode_number = req.episode_number or 1
    story_context = dict(req.story_bible)
    with get_db() as connection:
        characters = [
            {
                "name": row["name"],
                "role": row["role_type"],
                "personality": row["personality"],
                "backstory": row["backstory"],
                "visual_prompt": row["visual_prompt"],
                "voice": row["voice_profile"] or row["edge_tts_voice"],
            }
            for row in connection.execute(
                """
                SELECT name, role_type, personality, backstory, visual_prompt,
                       voice_profile, edge_tts_voice
                FROM characters WHERE project_id = ? ORDER BY id LIMIT 30
                """,
                (req.project_id,),
            ).fetchall()
        ]
        world_row = connection.execute(
            "SELECT * FROM worlds WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (req.project_id,),
        ).fetchone()
        previous_scenes = connection.execute(
            """
            SELECT episode_number, scene_number, title, dialogue
            FROM scenes WHERE project_id = ? AND episode_number < ?
            ORDER BY episode_number DESC, scene_number LIMIT 12
            """,
            (req.project_id, episode_number),
        ).fetchall()
        episode_row = connection.execute(
            """
            SELECT title, synopsis FROM episodes
            WHERE project_id = ? AND episode_number = ?
            """,
            (req.project_id, episode_number),
        ).fetchone()
    world_memory = None
    if world_row is not None:
        world_memory = {
            "name": world_row["name"],
            "setting": world_row["setting_description"],
            "time_period": world_row["time_period"],
            "factions": _decode_json(world_row["factions"], []),
            "locations": _decode_json(world_row["locations"], []),
            "rules": _decode_json(world_row["rules"], []),
        }
    story_context["_cinai_continuity"] = {
        "episode": {
            "number": episode_number,
            "title": episode_row["title"] if episode_row else f"Tập {episode_number}",
            "synopsis": episode_row["synopsis"] if episode_row else "",
        },
        "world_memory": world_memory,
        "character_memory": characters,
        "previous_episode_scenes": [
            {
                "episode": row["episode_number"],
                "scene": row["scene_number"],
                "title": row["title"],
                "dialogue": (row["dialogue"] or "")[:300],
            }
            for row in previous_scenes
        ],
        "instruction": (
            "Giữ nguyên tính cách, ngoại hình, luật thế giới và các sự kiện đã có. "
            "Tập mới phải tiếp nối các sự kiện trước; không tự ý đảo ngược dữ kiện."
        ),
    }
    try:
        result = provider.generate_script_and_scenes(
            story_context, episode_number
        )
    except (RuntimeError, json.JSONDecodeError, urllib.error.URLError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Lỗi từ {req.ai_provider}: {exc}"
        ) from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Gemini trả về dữ liệu không hợp lệ.")
    scenes = result.get("scenes", [])
    if not isinstance(scenes, list) or not scenes or not all(
        isinstance(scene, dict) for scene in scenes
    ):
        raise HTTPException(status_code=502, detail="Gemini không trả về danh sách cảnh hợp lệ.")
    script_text = result.get("fountain_script") or result.get("script")
    if script_text is not None and not isinstance(script_text, str):
        raise HTTPException(status_code=502, detail="Gemini trả về kịch bản không hợp lệ.")
    parsed_scenes = []
    seen_scene_numbers = set()
    for index, scene in enumerate(scenes, start=1):
        scene_number = scene.get("scene_number", index)
        try:
            scene_number = int(scene_number)
            duration = float(
                scene.get("estimated_duration") or scene.get("duration") or 5
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=502, detail="Gemini trả về số thứ tự/thời lượng cảnh không hợp lệ."
            ) from exc
        if scene_number < 1 or scene_number in seen_scene_numbers or not 0 < duration <= 300:
            raise HTTPException(
                status_code=502, detail="Gemini trả về thứ tự/thời lượng cảnh không hợp lệ."
            )
        seen_scene_numbers.add(scene_number)
        for field in (
            "scene_title",
            "title",
            "visual_prompt_en",
            "visual_prompt",
            "dialogue_vi",
            "dialogue",
            "camera_angle",
        ):
            if scene.get(field) is not None and not isinstance(scene[field], str):
                raise HTTPException(
                    status_code=502,
                    detail=f"Gemini trả về trường {field} không hợp lệ trong cảnh.",
                )
        parsed_scenes.append((scene, scene_number, duration))
    with get_db() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO episodes (project_id, episode_number, title)
            VALUES (?, ?, ?)
            """,
            (req.project_id, episode_number, f"Tập {episode_number}"),
        )
        generation_id = _insert_generation(
            connection, req.project_id, user["id"], "script",
            {**req.model_dump(), "story_context": story_context}, result
        )
        connection.execute(
            """
            INSERT INTO stories
                (project_id, episode_number, generation_id, fountain_script, data_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                req.project_id,
                req.episode_number or 1,
                generation_id,
                script_text,
                json.dumps(result, ensure_ascii=False),
            ),
        )
        for scene, scene_number, duration in parsed_scenes:
            connection.execute(
                """
                INSERT INTO scenes
                    (project_id, episode_number, generation_id, scene_number, title, visual_prompt, dialogue,
                     camera_angle, sfx, duration, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')
                """,
                (
                    req.project_id,
                    req.episode_number or 1,
                    generation_id,
                    scene_number,
                    scene.get("scene_title") or scene.get("title"),
                    scene.get("visual_prompt_en") or scene.get("visual_prompt"),
                    scene.get("dialogue_vi") or scene.get("dialogue"),
                    scene.get("camera_angle"),
                    json.dumps(scene.get("sound_fx"), ensure_ascii=False)
                    if scene.get("sound_fx") is not None
                    else None,
                    duration,
                ),
            )
    return result


def _insert_generation(
    connection, project_id: int, user_id: int, step: str, inputs: dict, output: dict
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO ai_generations
            (user_id, project_id, step, input_json, output_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            project_id,
            step,
            json.dumps(inputs, ensure_ascii=False),
            json.dumps(output, ensure_ascii=False),
        ),
    )
    return int(cursor.lastrowid)


def _save_generation(
    project_id: int, user_id: int, step: str, inputs: dict, output: dict
) -> None:
    with get_db() as connection:
        _insert_generation(connection, project_id, user_id, step, inputs, output)
