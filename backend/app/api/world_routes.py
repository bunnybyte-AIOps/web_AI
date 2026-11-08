# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3
import json

router = APIRouter(tags=["Worlds"])

DB_PATH = "d:/DACS2/backend/cinai.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class WorldCreate(BaseModel):
    name: str
    setting_description: Optional[str] = None
    time_period: Optional[str] = None
    technology_level: Optional[str] = None
    factions: Optional[str] = None   # JSON string
    locations: Optional[str] = None  # JSON string
    rules: Optional[str] = None      # JSON string


@router.get("/projects/{project_id}/worlds")
def get_worlds(project_id: int):
    """Lấy thông tin thế giới quan của dự án."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM worlds WHERE project_id = ? ORDER BY id", (project_id,))
        rows = c.fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            for field in ["factions", "locations", "rules"]:
                if d.get(field):
                    try:
                        d[field] = json.loads(d[field])
                    except Exception:
                        pass
            result.append(d)
        return {"status": "ok", "data": result, "total": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/worlds")
def create_world(project_id: int, item: WorldCreate):
    """Tạo hoặc cập nhật thế giới quan cho dự án."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO worlds (project_id, name, setting_description, time_period,
                technology_level, factions, locations, rules)
            VALUES (?,?,?,?,?,?,?,?)
        """, (project_id, item.name, item.setting_description, item.time_period,
              item.technology_level, item.factions, item.locations, item.rules))
        conn.commit()
        new_id = c.lastrowid
        c.execute("SELECT * FROM worlds WHERE id = ?", (new_id,))
        row = c.fetchone()
        conn.close()
        d = dict(row)
        for field in ["factions", "locations", "rules"]:
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    pass
        return {"status": "ok", "data": d}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
