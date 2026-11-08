from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.security import get_current_user, require_project_owner

router = APIRouter(prefix="/projects", tags=["Projects Management"])


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: Optional[str] = Field(default="", max_length=5000)
    genre: Optional[str] = Field(default="Điện ảnh", max_length=80)


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=5000)
    genre: Optional[str] = Field(default=None, max_length=80)
    status: Optional[str] = Field(default=None, max_length=40)


@router.get("/")
def list_projects(user: dict = Depends(get_current_user)) -> list[dict]:
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM scenes s WHERE s.project_id = p.id) AS scene_count,
                   (SELECT COUNT(*) FROM assets a WHERE a.project_id = p.id) AS asset_count
            FROM projects p WHERE p.user_id = ? ORDER BY p.id DESC
            """,
            (user["id"],),
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/", status_code=201)
def create_project(
    item: ProjectCreate, user: dict = Depends(get_current_user)
) -> dict:
    with get_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO projects (user_id, title, description, genre, status)
            VALUES (?, ?, ?, ?, 'draft')
            """,
            (user["id"], item.title.strip(), item.description, item.genre),
        )
        project_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO seasons (project_id, season_number, title)
            VALUES (?, 1, 'Mùa 1')
            """,
            (project_id,),
        )
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return dict(row)


@router.put("/{project_id}")
def update_project(
    project_id: int,
    item: ProjectUpdate,
    user: dict = Depends(get_current_user),
) -> dict:
    require_project_owner(project_id, user["id"])
    updates = item.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Không có trường nào để cập nhật.")
    if "title" in updates:
        updates["title"] = updates["title"].strip()
        if not updates["title"]:
            raise HTTPException(status_code=422, detail="Tên dự án không được để trống.")
    assignments = ", ".join(f"{field} = ?" for field in updates)
    with get_db() as connection:
        connection.execute(
            f"UPDATE projects SET {assignments} WHERE id = ? AND user_id = ?",
            (*updates.values(), project_id, user["id"]),
        )
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return dict(row)


@router.delete("/{project_id}")
def delete_project(
    project_id: int, user: dict = Depends(get_current_user)
) -> dict[str, str]:
    require_project_owner(project_id, user["id"])
    child_tables = (
        "social_oauth_states",
        "social_connections",
        "story_bibles",
        "stories",
        "scenes",
        "episodes",
        "seasons",
        "characters",
        "worlds",
        "assets",
        "ai_generations",
        "analytics",
        "ai_recommendations",
        "video_renders",
    )
    with get_db() as connection:
        for table in child_tables:
            connection.execute(
                f"DELETE FROM {table} WHERE project_id = ?", (project_id,)
            )
        connection.execute(
            "DELETE FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["id"]),
        )
    return {"message": "Xóa dự án thành công"}
