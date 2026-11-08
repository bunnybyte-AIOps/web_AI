# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import sqlite3
import json

router = APIRouter(tags=["Assets"])

DB_PATH = "d:/DACS2/backend/cinai.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class AssetCreate(BaseModel):
    name: str
    asset_type: Optional[str] = "visual"
    file_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    file_size_mb: Optional[float] = 0.0
    duration_seconds: Optional[float] = None
    tags: Optional[str] = None  # JSON string


class AssetStatusUpdate(BaseModel):
    status: str


@router.get("/projects/{project_id}/assets")
def list_assets(
    project_id: int,
    asset_type: Optional[str] = Query(None, description="Lọc theo loại: visual, audio, sfx, background")
):
    """Danh sách tài nguyên của dự án, có thể lọc theo loại."""
    try:
        conn = get_db()
        c = conn.cursor()
        if asset_type:
            c.execute("""
                SELECT * FROM assets WHERE project_id = ? AND asset_type = ?
                ORDER BY created_at DESC
            """, (project_id, asset_type))
        else:
            c.execute("""
                SELECT * FROM assets WHERE project_id = ?
                ORDER BY created_at DESC
            """, (project_id,))
        rows = c.fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("tags"):
                try:
                    d["tags"] = json.loads(d["tags"])
                except Exception:
                    pass
            result.append(d)
        return {"status": "ok", "data": result, "total": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/assets")
def create_asset(project_id: int, item: AssetCreate):
    """Thêm tài nguyên mới vào dự án."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO assets (project_id, name, asset_type, file_url, thumbnail_url,
                file_size_mb, duration_seconds, tags)
            VALUES (?,?,?,?,?,?,?,?)
        """, (project_id, item.name, item.asset_type, item.file_url,
              item.thumbnail_url, item.file_size_mb, item.duration_seconds, item.tags))
        conn.commit()
        new_id = c.lastrowid
        c.execute("SELECT * FROM assets WHERE id = ?", (new_id,))
        row = c.fetchone()
        conn.close()
        d = dict(row)
        if d.get("tags"):
            try:
                d["tags"] = json.loads(d["tags"])
            except Exception:
                pass
        return {"status": "ok", "data": d}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/assets/{asset_id}/status")
def update_asset_status(asset_id: int, item: AssetStatusUpdate):
    """Cập nhật trạng thái tài nguyên."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE assets SET status = ? WHERE id = ?", (item.status, asset_id))
        conn.commit()
        if c.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên")
        conn.close()
        return {"status": "ok", "message": f"Đã cập nhật trạng thái thành '{item.status}'"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
