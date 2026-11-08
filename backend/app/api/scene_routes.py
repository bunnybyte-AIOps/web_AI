# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3
import json

router = APIRouter(tags=["Scenes"])

DB_PATH = "d:/DACS2/backend/cinai.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class SceneCreate(BaseModel):
    scene_number: int
    title: Optional[str] = None
    visual_prompt: Optional[str] = None
    dialogue: Optional[str] = None
    camera_angle: Optional[str] = "medium_shot"
    sfx: Optional[str] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    duration: Optional[float] = 5.0


class SceneUpdate(BaseModel):
    scene_number: Optional[int] = None
    title: Optional[str] = None
    visual_prompt: Optional[str] = None
    dialogue: Optional[str] = None
    camera_angle: Optional[str] = None
    sfx: Optional[str] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    status: Optional[str] = None


def _parse_scene(row: dict) -> dict:
    for field in ["dialogue", "sfx"]:
        if row.get(field):
            try:
                row[field] = json.loads(row[field])
            except Exception:
                pass
    return row


@router.get("/projects/{project_id}/scenes")
def list_scenes(project_id: int):
    """Danh sách tất cả cảnh quay của dự án."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_number", (project_id,))
        rows = c.fetchall()
        conn.close()
        result = [_parse_scene(dict(r)) for r in rows]
        return {"status": "ok", "data": result, "total": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/scenes")
def create_scene(project_id: int, item: SceneCreate):
    """Thêm cảnh quay mới vào dự án."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO scenes (project_id, scene_number, title, visual_prompt, dialogue,
                camera_angle, sfx, image_url, audio_url, duration)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (project_id, item.scene_number, item.title, item.visual_prompt,
              item.dialogue, item.camera_angle, item.sfx,
              item.image_url, item.audio_url, item.duration))
        conn.commit()
        new_id = c.lastrowid
        c.execute("SELECT * FROM scenes WHERE id = ?", (new_id,))
        row = c.fetchone()
        conn.close()
        return {"status": "ok", "data": _parse_scene(dict(row))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/scenes/{scene_id}")
def update_scene(scene_id: int, item: SceneUpdate):
    """Cập nhật thông tin cảnh quay."""
    try:
        conn = get_db()
        c = conn.cursor()
        updates = {k: v for k, v in item.dict().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="Không có trường nào để cập nhật")
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [scene_id]
        c.execute(f"UPDATE scenes SET {set_clause} WHERE id = ?", values)
        conn.commit()
        if c.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Không tìm thấy cảnh quay")
        c.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,))
        row = c.fetchone()
        conn.close()
        return {"status": "ok", "data": _parse_scene(dict(row))}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scenes/{scene_id}")
def delete_scene(scene_id: int):
    """Xóa cảnh quay."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
        conn.commit()
        if c.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Không tìm thấy cảnh quay")
        conn.close()
        return {"status": "ok", "message": "Đã xóa cảnh quay thành công"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
