# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3

router = APIRouter(tags=["Characters"])

DB_PATH = "d:/DACS2/backend/cinai.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class CharacterCreate(BaseModel):
    name: str
    role_type: Optional[str] = "supporting"
    age: Optional[int] = None
    voice_profile: Optional[str] = None
    visual_prompt: Optional[str] = None
    personality: Optional[str] = None
    backstory: Optional[str] = None
    flux_prompt: Optional[str] = None
    edge_tts_voice: Optional[str] = None


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    role_type: Optional[str] = None
    age: Optional[int] = None
    voice_profile: Optional[str] = None
    visual_prompt: Optional[str] = None
    personality: Optional[str] = None
    backstory: Optional[str] = None
    flux_prompt: Optional[str] = None
    edge_tts_voice: Optional[str] = None
    status: Optional[str] = None


@router.get("/projects/{project_id}/characters")
def list_characters(project_id: int):
    """Danh sách nhân vật của dự án."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM characters WHERE project_id = ? ORDER BY id", (project_id,))
        rows = c.fetchall()
        conn.close()
        return {"status": "ok", "data": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/characters")
def create_character(project_id: int, item: CharacterCreate):
    """Tạo nhân vật mới cho dự án."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO characters (project_id, name, role_type, age, voice_profile,
                visual_prompt, personality, backstory, flux_prompt, edge_tts_voice)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (project_id, item.name, item.role_type, item.age, item.voice_profile,
              item.visual_prompt, item.personality, item.backstory,
              item.flux_prompt, item.edge_tts_voice))
        conn.commit()
        new_id = c.lastrowid
        c.execute("SELECT * FROM characters WHERE id = ?", (new_id,))
        row = c.fetchone()
        conn.close()
        return {"status": "ok", "data": dict(row)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/characters/{char_id}")
def update_character(char_id: int, item: CharacterUpdate):
    """Cập nhật thông tin nhân vật."""
    try:
        conn = get_db()
        c = conn.cursor()
        updates = {k: v for k, v in item.dict().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="Không có trường nào để cập nhật")
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [char_id]
        c.execute(f"UPDATE characters SET {set_clause} WHERE id = ?", values)
        conn.commit()
        if c.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân vật")
        c.execute("SELECT * FROM characters WHERE id = ?", (char_id,))
        row = c.fetchone()
        conn.close()
        return {"status": "ok", "data": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/characters/{char_id}")
def delete_character(char_id: int):
    """Xóa nhân vật."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM characters WHERE id = ?", (char_id,))
        conn.commit()
        if c.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân vật")
        conn.close()
        return {"status": "ok", "message": "Đã xóa nhân vật thành công"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
