import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, require_project_owner

router = APIRouter(prefix="/social", tags=["Social Analytics"])
PLATFORMS = {"youtube", "tiktok", "facebook", "instagram"}
SOCIAL_SCOPES = {
    "youtube": "https://www.googleapis.com/auth/yt-analytics.readonly https://www.googleapis.com/auth/youtube.readonly",
    "tiktok": "user.info.basic,video.list",
    "facebook": "pages_show_list,pages_read_engagement,read_insights",
    "instagram": "pages_show_list,pages_read_engagement,instagram_basic,instagram_manage_insights",
}


def _client_credentials(platform: str) -> tuple[str | None, str | None]:
    if platform == "youtube":
        return settings.SOCIAL_YOUTUBE_CLIENT_ID, settings.SOCIAL_YOUTUBE_CLIENT_SECRET
    if platform == "tiktok":
        return settings.TIKTOK_CLIENT_KEY, settings.TIKTOK_CLIENT_SECRET
    return settings.META_APP_ID, settings.META_APP_SECRET


def _redirect_uri(platform: str) -> str:
    return f"{settings.SOCIAL_OAUTH_BASE_URL}/api/social/{platform}/callback"


def _configured(platform: str) -> bool:
    client_id, client_secret = _client_credentials(platform)
    return bool(client_id and client_secret)


def _fernet() -> Fernet:
    key = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    import base64

    return Fernet(base64.urlsafe_b64encode(key))


def _encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def _decrypt_token(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Không thể giải mã token mạng xã hội. Kiểm tra SECRET_KEY của máy chủ.",
        ) from exc


def _json_request(
    url: str,
    *,
    method: str = "GET",
    data: dict[str, str] | None = None,
    json_data: dict[str, Any] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if json_data is not None:
        body = json.dumps(json_data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Nền tảng từ chối yêu cầu (HTTP {exc.code}). Kiểm tra quyền OAuth và cấu hình ứng dụng.",
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(
            status_code=502, detail="Không thể kết nối API của nền tảng mạng xã hội."
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502, detail="Nền tảng trả về dữ liệu không hợp lệ."
        ) from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Nền tảng trả về dữ liệu không hợp lệ.")
    api_error = result.get("error")
    if _has_api_error(api_error):
        message = api_error.get("message") if isinstance(api_error, dict) else str(api_error)
        raise HTTPException(
            status_code=502, detail=f"Lỗi API mạng xã hội: {str(message)[:300]}"
        )
    return result


def _has_api_error(value: Any) -> bool:
    if not value or value == "ok":
        return False
    return not (isinstance(value, dict) and value.get("code") in {"ok", ""})


def _exchange_code(platform: str, code: str) -> dict[str, Any]:
    client_id, client_secret = _client_credentials(platform)
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail=f"Chưa cấu hình OAuth cho {platform}.")
    redirect_uri = _redirect_uri(platform)
    if platform == "youtube":
        token_data = _json_request(
            "https://oauth2.googleapis.com/token",
            method="POST",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    elif platform == "tiktok":
        token_data = _json_request(
            "https://open.tiktokapis.com/v2/oauth/token/",
            method="POST",
            data={
                "code": code,
                "client_key": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if _has_api_error(token_data.get("error")):
            raise HTTPException(status_code=502, detail="TikTok không hoàn tất OAuth.")
        token_data = token_data.get("data", token_data)
    else:
        token_data = _json_request(
            f"https://graph.facebook.com/{settings.META_GRAPH_VERSION}/oauth/access_token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
        )
        short_token = token_data.get("access_token")
        if short_token:
            token_data = _json_request(
                f"https://graph.facebook.com/{settings.META_GRAPH_VERSION}/oauth/access_token?"
                + urllib.parse.urlencode(
                    {
                        "grant_type": "fb_exchange_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "fb_exchange_token": short_token,
                    }
                )
            )
    if not token_data.get("access_token"):
        raise HTTPException(status_code=502, detail="Nền tảng không trả về access token.")
    return token_data


def _account_for_platform(platform: str, token: str) -> tuple[str, str, str]:
    if platform == "youtube":
        result = _json_request(
            "https://www.googleapis.com/youtube/v3/channels?part=id%2Csnippet&mine=true",
            token=token,
        )
        items = result.get("items") or []
        if not items:
            raise HTTPException(status_code=502, detail="Tài khoản Google chưa có kênh YouTube.")
        item = items[0]
        return str(item["id"]), str(item.get("snippet", {}).get("title") or "YouTube"), token
    if platform == "tiktok":
        result = _json_request(
            "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name",
            token=token,
        )
        user = result.get("data", {}).get("user", {})
        if not user.get("open_id"):
            raise HTTPException(status_code=502, detail="Không đọc được tài khoản TikTok.")
        return str(user["open_id"]), str(user.get("display_name") or "TikTok"), token

    result = _json_request(
        f"https://graph.facebook.com/{settings.META_GRAPH_VERSION}/me/accounts?"
        + urllib.parse.urlencode(
            {"fields": "id,name,access_token,instagram_business_account"}
        ),
        token=token,
    )
    pages = result.get("data") or []
    for page in pages:
        instagram = page.get("instagram_business_account") or {}
        if platform == "facebook" and page.get("id"):
            return str(page["id"]), str(page.get("name") or "Facebook Page"), str(
                page.get("access_token") or token
            )
        if platform == "instagram" and instagram.get("id"):
            return str(instagram["id"]), str(page.get("name") or "Instagram"), str(
                page.get("access_token") or token
            )
    requested = "Instagram Business/Creator" if platform == "instagram" else "Facebook Page"
    raise HTTPException(
        status_code=502,
        detail=f"Tài khoản chưa có {requested} được cấp quyền cho ứng dụng Meta.",
    )


@router.get("/projects/{project_id}/connections")
def list_social_connections(
    project_id: int, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT id, platform, account_id, account_name, created_at, updated_at
            FROM social_connections
            WHERE project_id = ? AND user_id = ?
            ORDER BY platform, id
            """,
            (project_id, user["id"]),
        ).fetchall()
    return {
        "available_platforms": [
            {"platform": platform, "configured": _configured(platform)}
            for platform in sorted(PLATFORMS)
        ],
        "connections": [dict(row) for row in rows],
    }


@router.get("/projects/{project_id}/{platform}/connect")
def start_social_connection(
    project_id: int,
    platform: str,
    user: dict = Depends(get_current_user),
) -> RedirectResponse:
    require_project_owner(project_id, user["id"])
    if platform not in PLATFORMS:
        raise HTTPException(status_code=404, detail="Nền tảng chưa được hỗ trợ.")
    client_id, client_secret = _client_credentials(platform)
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail=f"Chưa cấu hình ứng dụng OAuth cho {platform}. Thêm thông tin vào backend/.env rồi khởi động lại.",
        )

    state = secrets.token_urlsafe(32)
    now = int(time.time())
    with get_db() as connection:
        connection.execute("DELETE FROM social_oauth_states WHERE expires_at < ?", (now,))
        connection.execute(
            """
            INSERT INTO social_oauth_states
                (state, project_id, user_id, platform, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (state, project_id, user["id"], platform, now + 600, now),
        )
    redirect_uri = _redirect_uri(platform)
    if platform == "youtube":
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        query = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SOCIAL_SCOPES[platform],
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    elif platform == "tiktok":
        auth_url = "https://www.tiktok.com/v2/auth/authorize/"
        query = {
            "client_key": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SOCIAL_SCOPES[platform],
            "state": state,
        }
    else:
        auth_url = f"https://www.facebook.com/{settings.META_GRAPH_VERSION}/dialog/oauth"
        query = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SOCIAL_SCOPES[platform],
            "state": state,
        }
    return RedirectResponse(f"{auth_url}?{urllib.parse.urlencode(query)}", status_code=302)


@router.get("/{platform}/callback")
def complete_social_connection(
    platform: str,
    state: str,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if platform not in PLATFORMS:
        raise HTTPException(status_code=404, detail="Nền tảng chưa được hỗ trợ.")
    now = int(time.time())
    with get_db() as connection:
        state_row = connection.execute(
            """
            SELECT * FROM social_oauth_states
            WHERE state = ? AND platform = ? AND expires_at > ?
            """,
            (state, platform, now),
        ).fetchone()
        if state_row is None:
            raise HTTPException(status_code=400, detail="OAuth state không hợp lệ hoặc đã hết hạn.")
        connection.execute("DELETE FROM social_oauth_states WHERE id = ?", (state_row["id"],))
    studio_url = f"{settings.SOCIAL_OAUTH_BASE_URL}/studio?tab=analytics"
    if error or not code:
        return RedirectResponse(f"{studio_url}&social=cancelled", status_code=303)

    token_data = _exchange_code(platform, code)
    access_token = str(token_data["access_token"])
    account_id, account_name, account_token = _account_for_platform(platform, access_token)
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")
    expires_at = now + int(expires_in) if expires_in else None
    with get_db() as connection:
        connection.execute(
            """
            INSERT INTO social_connections
                (project_id, user_id, platform, account_id, account_name,
                 access_token, refresh_token, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, platform, account_id) DO UPDATE SET
                user_id = excluded.user_id,
                account_name = excluded.account_name,
                access_token = excluded.access_token,
                refresh_token = COALESCE(excluded.refresh_token, social_connections.refresh_token),
                expires_at = excluded.expires_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                state_row["project_id"],
                state_row["user_id"],
                platform,
                account_id,
                account_name,
                _encrypt_token(account_token),
                refresh_token,
                expires_at,
            ),
        )
    return RedirectResponse(f"{studio_url}&social=connected", status_code=303)


def _refresh_token(connection: dict[str, Any]) -> tuple[str, int | None]:
    token = _decrypt_token(connection["access_token"])
    if not connection.get("expires_at") or int(connection["expires_at"]) > int(time.time()) + 60:
        return token, connection.get("expires_at")
    refresh = connection.get("refresh_token")
    client_id, client_secret = _client_credentials(connection["platform"])
    if not refresh or not client_id or not client_secret:
        raise HTTPException(
            status_code=409,
            detail="OAuth token đã hết hạn. Hãy kết nối lại tài khoản mạng xã hội.",
        )
    if connection["platform"] == "youtube":
        token_data = _json_request(
            "https://oauth2.googleapis.com/token",
            method="POST",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
    elif connection["platform"] == "tiktok":
        token_data = _json_request(
            "https://open.tiktokapis.com/v2/oauth/token/",
            method="POST",
            data={
                "client_key": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh,
            },
        )
        if _has_api_error(token_data.get("error")):
            raise HTTPException(status_code=502, detail="TikTok không thể làm mới token OAuth.")
        token_data = token_data.get("data", token_data)
    else:
        raise HTTPException(
            status_code=409,
            detail="Token Meta hết hạn. Hãy kết nối lại tài khoản Facebook/Instagram.",
        )
    refreshed = str(token_data.get("access_token") or "")
    if not refreshed:
        raise HTTPException(status_code=502, detail="Nền tảng không làm mới được token.")
    expires_in = token_data.get("expires_in")
    expires_at = int(time.time()) + int(expires_in) if expires_in else None
    with get_db() as db:
        db.execute(
            """
            UPDATE social_connections
            SET access_token = ?, refresh_token = COALESCE(?, refresh_token),
                expires_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                _encrypt_token(refreshed),
                token_data.get("refresh_token"),
                expires_at,
                connection["id"],
            ),
        )
    return refreshed, expires_at


def _youtube_rows(token: str, days: int) -> list[dict[str, Any]]:
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    raw_rows = []
    start_index = 1
    while start_index <= 10_000:
        query = urllib.parse.urlencode(
            {
                "ids": "channel==MINE",
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "metrics": "views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares",
                "dimensions": "video",
                "sort": "-views",
                "maxResults": "200",
                "startIndex": str(start_index),
            }
        )
        result = _json_request(
            f"https://youtubeanalytics.googleapis.com/v2/reports?{query}",
            token=token,
        )
        page_rows = result.get("rows", [])
        raw_rows.extend(page_rows)
        if len(page_rows) < 200:
            break
        start_index += 200
    return [
        {
            "external_content_id": str(row[0]),
            "view_count": int(row[1] or 0),
            "watch_time_avg_sec": float(row[3] or 0),
            "like_count": int(row[4] or 0),
            "comment_count": int(row[5] or 0),
            "share_count": int(row[6] or 0),
            "unique_viewers": 0,
            "retention_rate": 0,
        }
        for row in raw_rows
        if len(row) >= 7
    ]


def _tiktok_rows(token: str, days: int) -> list[dict[str, Any]]:
    fields = "id,create_time,video_description,view_count,like_count,comment_count,share_count"
    videos = []
    cursor = None
    for page in range(50):
        body: dict[str, Any] = {"max_count": 20}
        if cursor is not None:
            body["cursor"] = cursor
        result = _json_request(
            "https://open.tiktokapis.com/v2/video/list/?"
            + urllib.parse.urlencode({"fields": fields}),
            method="POST",
            json_data=body,
            token=token,
        )
        data = result.get("data", {})
        videos.extend(data.get("videos", []))
        next_cursor = data.get("cursor")
        if not data.get("has_more") or next_cursor is None or next_cursor == cursor:
            break
        if page == 49:
            raise HTTPException(
                status_code=502, detail="TikTok trả về quá nhiều trang video cần đồng bộ."
            )
        cursor = next_cursor
    cutoff = int(time.time()) - days * 24 * 60 * 60
    return [
        {
            "external_content_id": str(video["id"]),
            "view_count": int(video.get("view_count") or 0),
            "watch_time_avg_sec": 0,
            "like_count": int(video.get("like_count") or 0),
            "comment_count": int(video.get("comment_count") or 0),
            "share_count": int(video.get("share_count") or 0),
            "unique_viewers": 0,
            "retention_rate": 0,
        }
        for video in videos
        if video.get("id") and int(video.get("create_time") or 0) >= cutoff
    ]


def _meta_pages(url: str, token: str) -> list[dict[str, Any]]:
    rows = []
    next_url: str | None = url
    for page in range(50):
        if not next_url:
            break
        parsed_url = urllib.parse.urlsplit(next_url)
        if parsed_url.scheme != "https" or parsed_url.hostname != "graph.facebook.com":
            raise HTTPException(
                status_code=502, detail="Meta trả về đường dẫn phân trang không hợp lệ."
            )
        query = urllib.parse.parse_qsl(parsed_url.query, keep_blank_values=True)
        safe_query = urllib.parse.urlencode(
            [(key, value) for key, value in query if key.lower() != "access_token"]
        )
        safe_url = urllib.parse.urlunsplit(parsed_url._replace(query=safe_query))
        result = _json_request(safe_url, token=token)
        rows.extend(result.get("data", []))
        next_url = result.get("paging", {}).get("next")
        if page == 49 and next_url:
            raise HTTPException(
                status_code=502, detail="Meta trả về quá nhiều trang cần đồng bộ."
            )
    return rows


def _meta_rows(
    platform: str, account_id: str, token: str, days: int
) -> list[dict[str, Any]]:
    version = settings.META_GRAPH_VERSION
    cutoff = date.today() - timedelta(days=days)
    if platform == "facebook":
        endpoint = f"https://graph.facebook.com/{version}/{urllib.parse.quote(account_id)}/posts?"
        query = urllib.parse.urlencode(
            {
                "fields": "id,created_time,shares,likes.summary(true),comments.summary(true),insights.metric(post_impressions,post_video_views)",
                "limit": "100",
                "since": str(int(time.time()) - days * 24 * 60 * 60),
            }
        )
        posts = _meta_pages(endpoint + query, token)
        rows = []
        for post in posts:
            created = post.get("created_time")
            if created:
                try:
                    created_date = date.fromisoformat(str(created)[:10])
                except ValueError:
                    continue
                if created_date < cutoff:
                    continue
            insights = {
                item.get("name"): item.get("values", [{}])[0].get("value", 0)
                for item in post.get("insights", {}).get("data", [])
            }
            rows.append(
                {
                    "external_content_id": str(post.get("id")),
                    "view_count": int(insights.get("post_video_views") or insights.get("post_impressions") or 0),
                    "watch_time_avg_sec": 0,
                    "like_count": int(post.get("likes", {}).get("summary", {}).get("total_count") or 0),
                    "comment_count": int(post.get("comments", {}).get("summary", {}).get("total_count") or 0),
                    "share_count": int(post.get("shares", {}).get("count") or 0),
                    "unique_viewers": 0,
                    "retention_rate": 0,
                }
            )
        return rows

    endpoint = f"https://graph.facebook.com/{version}/{urllib.parse.quote(account_id)}/media?"
    query = urllib.parse.urlencode(
        {"fields": "id,timestamp,like_count,comments_count,media_type", "limit": "100"}
    )
    rows = []
    for media in _meta_pages(endpoint + query, token):
        created = media.get("timestamp")
        if created:
            try:
                created_date = date.fromisoformat(str(created)[:10])
            except ValueError:
                continue
            if created_date < cutoff:
                continue
        media_id = media.get("id")
        if not media_id:
            continue
        insights = _json_request(
            f"https://graph.facebook.com/{version}/{urllib.parse.quote(str(media_id))}/insights?"
            + urllib.parse.urlencode(
                {
                    "metric": "reach,views,saved,shares",
                }
            ),
            token=token,
        ).get("data", [])
        values = {
            item.get("name"): item.get("values", [{}])[0].get("value", 0)
            for item in insights
        }
        rows.append(
            {
                "external_content_id": str(media_id),
                "view_count": int(values.get("views") or values.get("reach") or 0),
                "watch_time_avg_sec": 0,
                "like_count": int(media.get("like_count") or values.get("likes") or 0),
                "comment_count": int(media.get("comments_count") or values.get("comments") or 0),
                "share_count": int(values.get("shares") or 0),
                "unique_viewers": 0,
                "retention_rate": 0,
            }
        )
    return rows


@router.post("/projects/{project_id}/{platform}/sync")
def sync_social_analytics(
    project_id: int,
    platform: str,
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    require_project_owner(project_id, user["id"])
    if platform not in PLATFORMS:
        raise HTTPException(status_code=404, detail="Nền tảng chưa được hỗ trợ.")
    with get_db() as connection:
        linked = connection.execute(
            """
            SELECT * FROM social_connections
            WHERE project_id = ? AND user_id = ? AND platform = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (project_id, user["id"], platform),
        ).fetchone()
    if linked is None:
        raise HTTPException(status_code=409, detail="Hãy kết nối tài khoản trước khi đồng bộ.")
    account = dict(linked)
    token, _ = _refresh_token(account)
    if platform == "youtube":
        rows = _youtube_rows(token, days)
    elif platform == "tiktok":
        rows = _tiktok_rows(token, days)
    else:
        rows = _meta_rows(platform, account["account_id"], token, days)
    with get_db() as connection:
        for row in rows:
            connection.execute(
                """
                INSERT INTO analytics
                    (project_id, platform, external_content_id, view_count,
                     unique_viewers, watch_time_avg_sec, retention_rate,
                     like_count, comment_count, share_count, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, platform, external_content_id) DO UPDATE SET
                    view_count = excluded.view_count,
                    unique_viewers = excluded.unique_viewers,
                    watch_time_avg_sec = excluded.watch_time_avg_sec,
                    retention_rate = excluded.retention_rate,
                    like_count = excluded.like_count,
                    comment_count = excluded.comment_count,
                    share_count = excluded.share_count,
                    recorded_at = excluded.recorded_at
                """,
                (
                    project_id,
                    platform,
                    row["external_content_id"],
                    row["view_count"],
                    row["unique_viewers"],
                    row["watch_time_avg_sec"],
                    row["retention_rate"],
                    row["like_count"],
                    row["comment_count"],
                    row["share_count"],
                    date.today().isoformat(),
                ),
            )
        if rows:
            totals = {
                field: sum(row[field] for row in rows)
                for field in ("view_count", "like_count", "comment_count", "share_count")
            }
            connection.execute(
                "UPDATE projects SET view_count = ? WHERE id = ?",
                (totals["view_count"], project_id),
            )
        else:
            totals = {"view_count": 0, "like_count": 0, "comment_count": 0, "share_count": 0}
    return {
        "platform": platform,
        "account_name": account["account_name"],
        "synced": len(rows),
        "totals": totals,
    }


@router.delete("/projects/{project_id}/connections/{connection_id}")
def disconnect_social_account(
    project_id: int,
    connection_id: int,
    user: dict = Depends(get_current_user),
) -> dict[str, str]:
    require_project_owner(project_id, user["id"])
    with get_db() as connection:
        cursor = connection.execute(
            """
            DELETE FROM social_connections
            WHERE id = ? AND project_id = ? AND user_id = ?
            """,
            (connection_id, project_id, user["id"]),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản đã kết nối.")
    return {"message": "Đã ngắt kết nối tài khoản."}
