# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
import sqlite3

router = APIRouter(prefix="/users", tags=["Users"])

DB_PATH = "d:/DACS2/backend/cinai.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/stats/overview")
def platform_overview():
    """Tổng quan nền tảng: tổng users, projects, scenes, assets."""
    try:
        conn = get_db()
        c = conn.cursor()
        stats = {}
        for table in ["users", "projects", "scenes", "assets", "characters"]:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            stats[f"total_{table}"] = c.fetchone()[0]
        c.execute("SELECT SUM(view_count) FROM projects")
        stats["total_views"] = c.fetchone()[0] or 0
        c.execute("SELECT SUM(ai_credits) FROM users")
        stats["total_ai_credits_used"] = c.fetchone()[0] or 0
        c.execute("SELECT SUM(storage_used_mb) FROM users")
        stats["total_storage_used_mb"] = round(c.fetchone()[0] or 0, 2)
        conn.close()
        return {"status": "ok", "data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
def list_users():
    """Danh sách tất cả người dùng kèm thống kê."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT u.*,
                (SELECT COUNT(*) FROM projects p WHERE p.user_id = u.id) as project_count,
                (SELECT COUNT(*) FROM team_members tm WHERE tm.user_id = u.id) as team_count
            FROM users u
            ORDER BY u.id
        """)
        rows = c.fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d.pop("hashed_password", None)
            result.append(d)
        return {"status": "ok", "data": result, "total": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}")
def get_user(user_id: int):
    """Chi tiết một người dùng kèm hoạt động gần đây."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
        user = dict(row)
        user.pop("hashed_password", None)

        c.execute("""
            SELECT * FROM user_activities WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 10
        """, (user_id,))
        user["recent_activities"] = [dict(r) for r in c.fetchall()]

        c.execute("""
            SELECT p.id, p.title, p.genre, p.status, p.view_count, p.created_at
            FROM projects p WHERE p.user_id = ?
            ORDER BY p.created_at DESC
        """, (user_id,))
        user["projects"] = [dict(r) for r in c.fetchall()]

        conn.close()
        return {"status": "ok", "data": user}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/activities")
def get_user_activities(user_id: int, limit: int = 20):
    """Lấy hoạt động gần đây của người dùng."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT * FROM user_activities WHERE user_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (user_id, limit))
        rows = c.fetchall()
        conn.close()
        return {"status": "ok", "data": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
