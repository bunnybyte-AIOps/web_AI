# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
import sqlite3
import json

router = APIRouter(tags=["Analytics"])

DB_PATH = "d:/DACS2/backend/cinai.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/projects/{project_id}/analytics")
def get_project_analytics(project_id: int):
    """Lấy analytics và AI recommendations của dự án."""
    try:
        conn = get_db()
        c = conn.cursor()

        # Latest analytics row
        c.execute("""
            SELECT * FROM analytics WHERE project_id = ?
            ORDER BY recorded_at DESC LIMIT 1
        """, (project_id,))
        latest = c.fetchone()

        # All analytics history
        c.execute("""
            SELECT * FROM analytics WHERE project_id = ?
            ORDER BY recorded_at DESC LIMIT 30
        """, (project_id,))
        history = [dict(r) for r in c.fetchall()]

        # AI recommendations
        c.execute("""
            SELECT * FROM ai_recommendations WHERE project_id = ?
            ORDER BY priority DESC, created_at DESC
        """, (project_id,))
        recs = []
        for r in c.fetchall():
            d = dict(r)
            if d.get("data_json"):
                try:
                    d["data_json"] = json.loads(d["data_json"])
                except Exception:
                    pass
            recs.append(d)

        conn.close()
        return {
            "status": "ok",
            "data": {
                "latest": dict(latest) if latest else None,
                "history": history,
                "ai_recommendations": recs,
                "total_recommendations": len(recs)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/platform")
def get_platform_analytics():
    """Thống kê tổng hợp toàn nền tảng."""
    try:
        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
        active_users = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM projects")
        total_projects = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM projects WHERE status = 'published'")
        published_projects = c.fetchone()[0]

        c.execute("SELECT SUM(view_count) FROM projects")
        total_views = c.fetchone()[0] or 0

        c.execute("SELECT COUNT(*) FROM scenes")
        total_scenes = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM assets")
        total_assets = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM characters")
        total_characters = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM video_renders WHERE status = 'completed'")
        completed_renders = c.fetchone()[0]

        c.execute("SELECT SUM(file_size_mb) FROM video_renders WHERE status = 'completed'")
        total_render_size_mb = round(c.fetchone()[0] or 0, 2)

        # Top project by views
        c.execute("""
            SELECT p.id, p.title, p.view_count, u.full_name as creator
            FROM projects p
            JOIN users u ON p.user_id = u.id
            ORDER BY p.view_count DESC LIMIT 5
        """)
        top_projects = [dict(r) for r in c.fetchall()]

        conn.close()
        return {
            "status": "ok",
            "data": {
                "active_users": active_users,
                "total_projects": total_projects,
                "published_projects": published_projects,
                "total_views": total_views,
                "total_scenes": total_scenes,
                "total_assets": total_assets,
                "total_characters": total_characters,
                "completed_renders": completed_renders,
                "total_render_size_mb": total_render_size_mb,
                "top_projects_by_views": top_projects
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
