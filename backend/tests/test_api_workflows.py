import os
import json
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.parse
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import _configured_key, settings
from app.core.database import get_db, initialize_database
from app.core.security import hash_password
from app.api import social_routes
from app.main import app
from app.services.gemini_service import GeminiAPIError, gemini_orchestrator
from app.services.grok_service import grok_orchestrator
from app.services.otp_delivery import OTPDeliveryError


class SocialProviderAdapterTests(unittest.TestCase):
    def test_tiktok_success_error_code_is_not_treated_as_failure(self) -> None:
        self.assertFalse(social_routes._has_api_error({"code": "ok"}))

    def test_tiktok_video_pagination_uses_cursor_and_window(self) -> None:
        now = int(social_routes.time.time())
        with patch.object(
            social_routes,
            "_json_request",
            side_effect=[
                {"error": {"code": "ok"}, "data": {"videos": [], "has_more": True, "cursor": 42}},
                {
                    "error": {"code": "ok"},
                    "data": {
                        "videos": [
                            {
                                "id": "recent-video",
                                "create_time": now,
                                "view_count": 12,
                            },
                            {
                                "id": "old-video",
                                "create_time": now - 60 * 24 * 60 * 60,
                            },
                        ],
                        "has_more": False,
                        "cursor": 42,
                    },
                },
            ],
        ) as request:
            rows = social_routes._tiktok_rows("test-token", 30)

        self.assertEqual([row["external_content_id"] for row in rows], ["recent-video"])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[1].kwargs["json_data"]["cursor"], 42)

    def test_meta_pagination_removes_access_tokens_from_urls(self) -> None:
        next_page = "https://graph.facebook.com/v24.0/page/posts?after=next&access_token=leaked"
        with patch.object(
            social_routes,
            "_json_request",
            side_effect=[
                {"data": [{"id": "post-1"}], "paging": {"next": next_page}},
                {"data": [{"id": "post-2"}]},
            ],
        ) as request:
            rows = social_routes._meta_pages(
                "https://graph.facebook.com/v24.0/page/posts?access_token=initial",
                "test-token",
            )

        self.assertEqual([row["id"] for row in rows], ["post-1", "post-2"])
        for call in request.call_args_list:
            self.assertNotIn("access_token", call.args[0])
            self.assertEqual(call.kwargs["token"], "test-token")

    def test_meta_pagination_rejects_non_graph_hosts(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            social_routes._meta_pages("https://example.test/collect", "test-token")

        self.assertEqual(caught.exception.status_code, 502)


class GeminiServiceErrorTests(unittest.TestCase):
    def test_primary_timeout_is_converted_to_safe_provider_error(self) -> None:
        orchestrator = type(gemini_orchestrator)()
        orchestrator.api_key = "private-test-key"
        orchestrator.model = "primary-model"

        with patch(
            "app.services.gemini_service.urllib.request.urlopen",
            side_effect=TimeoutError(),
        ):
            with self.assertRaisesRegex(
                GeminiAPIError, "không phản hồi trong 45 giây"
            ) as caught:
                orchestrator._request_model("primary-model", {})

        self.assertNotIn("private-test-key", str(caught.exception))

    def test_primary_timeout_can_use_fallback(self) -> None:
        fallback_response = {
            "candidates": [
                {"content": {"parts": [{"text": '{"concepts": []}'}]}}
            ]
        }
        orchestrator = type(gemini_orchestrator)()
        orchestrator.api_key = "private-test-key"
        orchestrator.model = "primary-model"
        orchestrator.fallback_model = "fallback-model"

        with patch.object(
            orchestrator,
            "_request_model",
            side_effect=[
                GeminiAPIError(503, "primary timed out"),
                fallback_response,
            ],
        ) as request_model:
            result = orchestrator._call_gemini("", "test prompt")

        self.assertEqual(result, '{"concepts": []}')
        self.assertEqual(request_model.call_count, 2)

    def test_model_not_found_includes_provider_detail_without_key(self) -> None:
        response = Mock()
        response.read.return_value = (
            b'{"error":{"message":"Model not found for API version v1beta."}}'
        )
        error = urllib.error.HTTPError(
            url="https://generativelanguage.googleapis.com/",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=response,
        )
        orchestrator = type(gemini_orchestrator)()
        orchestrator.api_key = "private-test-key"
        orchestrator.model = "missing-model"

        with patch("app.services.gemini_service.urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "Model 'missing-model'") as caught:
                orchestrator._call_gemini("", "test")

        self.assertIn("Model not found for API version v1beta.", str(caught.exception))
        self.assertNotIn("private-test-key", str(caught.exception))

    def test_overloaded_primary_model_uses_fallback_model(self) -> None:
        primary_error = GeminiAPIError(
            503, "Gemini API trả về HTTP 503. Chi tiết từ Google: overloaded"
        )
        fallback_response = {
            "candidates": [
                {"content": {"parts": [{"text": '{"concepts": []}'}]}}
            ]
        }
        orchestrator = type(gemini_orchestrator)()
        orchestrator.api_key = "private-test-key"
        orchestrator.model = "primary-model"
        orchestrator.fallback_model = "fallback-model"

        with patch.object(
            orchestrator,
            "_request_model",
            side_effect=[primary_error, fallback_response],
        ) as request_model:
            result = orchestrator._call_gemini("", "test prompt")

        self.assertEqual(result, '{"concepts": []}')
        self.assertEqual(
            [call.args[0] for call in request_model.call_args_list],
            ["primary-model", "fallback-model"],
        )

    def test_non_transient_model_error_does_not_use_fallback(self) -> None:
        orchestrator = type(gemini_orchestrator)()
        orchestrator.api_key = "private-test-key"
        orchestrator.model = "primary-model"
        orchestrator.fallback_model = "fallback-model"

        with patch.object(
            orchestrator,
            "_request_model",
            side_effect=GeminiAPIError(404, "model unavailable"),
        ) as request_model:
            with self.assertRaisesRegex(GeminiAPIError, "model unavailable"):
                orchestrator._call_gemini("", "test prompt")

        request_model.assert_called_once()


class GeminiConfigurationTests(unittest.TestCase):
    @patch.dict(os.environ, {"GEMINI_API_KEY": "your_gemini_api_key_here"})
    @patch("app.core.config.dotenv_values", return_value={"GEMINI_API_KEY": "file-key"})
    def test_placeholder_environment_key_falls_back_to_env_file(self, dotenv_mock) -> None:
        self.assertEqual(_configured_key("GEMINI_API_KEY"), "file-key")
        dotenv_mock.assert_called_once()

    @patch.dict(os.environ, {"GEMINI_API_KEY": "environment-key"})
    @patch("app.core.config.dotenv_values", return_value={"GEMINI_API_KEY": "file-key"})
    def test_configured_environment_key_takes_precedence(self, dotenv_mock) -> None:
        self.assertEqual(_configured_key("GEMINI_API_KEY"), "environment-key")
        dotenv_mock.assert_not_called()

    @patch.dict(os.environ, {"GROK_XAI_API_KEY": "xai-test-key"}, clear=True)
    @patch("app.core.config.dotenv_values", return_value={})
    def test_xai_key_alias_is_supported(self, dotenv_mock) -> None:
        self.assertEqual(_configured_key("XAI_API_KEY"), "xai-test-key")
        dotenv_mock.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch(
        "app.core.config.dotenv_values",
        return_value={"GROK_XAI_API_KEY": "xai-file-test-key"},
    )
    def test_xai_key_alias_is_loaded_from_env_file(self, dotenv_mock) -> None:
        self.assertEqual(_configured_key("XAI_API_KEY"), "xai-file-test-key")
        dotenv_mock.assert_called_once()


class GrokServiceTests(unittest.TestCase):
    def test_invalid_xai_key_error_is_returned_without_exposing_key(self) -> None:
        response = Mock()
        response.read.return_value = json.dumps(
            {
                "code": "unauthorized",
                "error": "Incorrect API key provided.",
            }
        ).encode("utf-8")
        error = urllib.error.HTTPError(
            url="https://api.x.ai/v1/chat/completions",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=response,
        )
        orchestrator = type(grok_orchestrator)()
        orchestrator.api_key = "private-test-key"
        orchestrator.model = "grok-test"

        with patch("app.services.grok_service.urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(
                GeminiAPIError, "Incorrect API key provided."
            ) as caught:
                orchestrator._call_gemini("", "test")

        self.assertNotIn("private-test-key", str(caught.exception))

    def test_grok_uses_xai_chat_completions_and_reads_json_content(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "choices": [
                    {"message": {"content": '{"concepts": []}'}}
                ]
            }
        ).encode("utf-8")
        orchestrator = type(grok_orchestrator)()
        orchestrator.api_key = "private-test-key"
        orchestrator.model = "grok-test"

        with patch(
            "app.services.grok_service.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            result = orchestrator._call_gemini("system", "prompt")

        self.assertEqual(result, '{"concepts": []}')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.x.ai/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer private-test-key")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "grok-test")
        self.assertEqual(payload["response_format"], {"type": "json_object"})


class ApiWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = settings.DATABASE_PATH
        self.original_gemini_key = settings.GEMINI_API_KEY
        self.original_xai_key = settings.XAI_API_KEY
        self.original_stability_key = settings.STABILITY_API_KEY
        self.original_google_client_id = settings.GOOGLE_CLIENT_ID
        self.original_youtube_client_id = settings.SOCIAL_YOUTUBE_CLIENT_ID
        self.original_youtube_client_secret = settings.SOCIAL_YOUTUBE_CLIENT_SECRET
        self.original_tiktok_client_key = settings.TIKTOK_CLIENT_KEY
        self.original_tiktok_client_secret = settings.TIKTOK_CLIENT_SECRET
        self.original_meta_app_id = settings.META_APP_ID
        self.original_meta_app_secret = settings.META_APP_SECRET
        settings.DATABASE_PATH = Path(self.temp_dir.name) / "cinai-test.sqlite"
        settings.GEMINI_API_KEY = "unit-test-key"
        settings.XAI_API_KEY = None
        settings.STABILITY_API_KEY = None
        settings.GOOGLE_CLIENT_ID = None
        settings.SOCIAL_YOUTUBE_CLIENT_ID = None
        settings.SOCIAL_YOUTUBE_CLIENT_SECRET = None
        settings.TIKTOK_CLIENT_KEY = None
        settings.TIKTOK_CLIENT_SECRET = None
        settings.META_APP_ID = None
        settings.META_APP_SECRET = None
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        registration = self._register_account(
            "creator@example.test", "email", "Test Creator", "valid-test-password"
        )
        self.assertEqual(registration.status_code, 201, registration.text)
        self.headers = {
            "Authorization": f"Bearer {registration.json()['access_token']}"
        }
        project = self.client.post(
            "/api/projects/", json={"title": "Test project"}, headers=self.headers
        )
        self.assertEqual(project.status_code, 201, project.text)
        self.project_id = project.json()["id"]

    def _register_account(
        self, contact: str, channel: str, full_name: str, password: str
    ):
        with patch("app.api.auth_routes.send_otp") as send_otp:
            requested = self.client.post(
                "/api/auth/otp/request",
                json={"channel": channel, "contact": contact, "purpose": "register"},
            )
            if requested.status_code != 200:
                return requested
            code = send_otp.call_args.args[2]
        return self.client.post(
            "/api/auth/register/verify",
            json={
                "channel": channel,
                "contact": contact,
                "otp": code,
                "password": password,
                "full_name": full_name,
            },
        )

    def test_existing_users_survive_auth_schema_migration(self) -> None:
        active_database_path = settings.DATABASE_PATH
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite"
        settings.DATABASE_PATH = legacy_path
        try:
            connection = sqlite3.connect(legacy_path)
            connection.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    full_name TEXT,
                    role TEXT NOT NULL DEFAULT 'creator',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            stored_hash = hash_password("legacy-test-password")
            connection.execute(
                "INSERT INTO users (email, hashed_password, full_name) VALUES (?, ?, ?)",
                ("legacy@example.test", stored_hash, "Legacy User"),
            )
            connection.commit()
            connection.close()

            initialize_database()
            with get_db() as upgraded:
                legacy = upgraded.execute(
                    "SELECT * FROM users WHERE email = ?", ("legacy@example.test",)
                ).fetchone()
            self.assertEqual(legacy["hashed_password"], stored_hash)
            self.assertEqual(legacy["email_verified"], 1)
            self.assertEqual(legacy["phone_verified"], 0)
        finally:
            settings.DATABASE_PATH = active_database_path

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        settings.DATABASE_PATH = self.original_database_path
        settings.GEMINI_API_KEY = self.original_gemini_key
        settings.XAI_API_KEY = self.original_xai_key
        settings.STABILITY_API_KEY = self.original_stability_key
        settings.GOOGLE_CLIENT_ID = self.original_google_client_id
        settings.SOCIAL_YOUTUBE_CLIENT_ID = self.original_youtube_client_id
        settings.SOCIAL_YOUTUBE_CLIENT_SECRET = self.original_youtube_client_secret
        settings.TIKTOK_CLIENT_KEY = self.original_tiktok_client_key
        settings.TIKTOK_CLIENT_SECRET = self.original_tiktok_client_secret
        settings.META_APP_ID = self.original_meta_app_id
        settings.META_APP_SECRET = self.original_meta_app_secret
        self.temp_dir.cleanup()

    def test_landing_and_studio_are_served_from_their_source_files(self) -> None:
        landing = self.client.get("/")
        studio = self.client.get("/studio?tab=analytics")
        studio_html = self.client.get("/studio.html")

        self.assertEqual(landing.status_code, 200)
        self.assertEqual(studio.status_code, 200)
        self.assertEqual(studio_html.status_code, 200)
        self.assertEqual(studio.text, studio_html.text)
        self.assertNotEqual(landing.text, studio.text)
        self.assertIn('id="cinai-landing-page"', landing.text)
        self.assertIn('id="cinai-studio-frame"', landing.text)
        self.assertIn("cinai-studio-route", landing.text)
        self.assertIn("hashchange", landing.text)
        self.assertIn("studio.html", landing.text)
        self.assertIn('href="/?auth=login#studio"', landing.text)
        self.assertIn('href="/#studio"', landing.text)
        self.assertIn("Nghe thử (chưa hỗ trợ)", studio.text)

    def test_scene_can_be_created_for_selected_episode_and_updated(self) -> None:
        created = self.client.post(
            f"/api/projects/{self.project_id}/scenes",
            json={
                "scene_number": 1,
                "title": "Cảnh ban đầu",
                "episode_number": 2,
            },
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201, created.text)
        scene_id = created.json()["id"]
        self.assertEqual(created.json()["episode_number"], 2)

        updated = self.client.put(
            f"/api/projects/{self.project_id}/scenes/{scene_id}",
            json={"title": "Cảnh đã sửa", "dialogue": "Lời thoại mới"},
            headers=self.headers,
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["title"], "Cảnh đã sửa")
        self.assertEqual(updated.json()["dialogue"], "Lời thoại mới")
        self.assertEqual(updated.json()["episode_number"], 2)

        scenes = self.client.get(
            f"/api/projects/{self.project_id}/scenes?episode_number=2",
            headers=self.headers,
        )
        self.assertEqual(scenes.status_code, 200, scenes.text)
        self.assertEqual([scene["title"] for scene in scenes.json()], ["Cảnh đã sửa"])

        empty_update = self.client.put(
            f"/api/projects/{self.project_id}/scenes/{scene_id}",
            json={},
            headers=self.headers,
        )
        self.assertEqual(empty_update.status_code, 400, empty_update.text)

    def test_local_frontend_origin_can_call_api_with_credentials(self) -> None:
        response = self.client.options(
            "/api/auth/login",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://127.0.0.1:5173",
        )
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")

    def _create_story_and_script(self) -> None:
        concepts = {
            "concepts": [
                {"title": "Test concept", "logline": "A test story."}
            ]
        }
        with patch.object(gemini_orchestrator, "generate_concepts", return_value=concepts):
            response = self.client.post(
                "/api/ai/ideas/generate",
                json={
                    "project_id": self.project_id,
                    "raw_idea": "A story about a lost signal",
                    "genre": "Sci-Fi",
                },
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 200, response.text)

        bible = {
            "logline": "A test story.",
            "world_bible": {
                "world_name": "Test World",
                "era_setting": "Near future",
                "rules_and_lore": ["Rule one"],
            },
            "character_bible": [
                {
                    "name": "Ari",
                    "role": "Protagonist",
                    "visual_prompt": "A pilot",
                    "voice_id": "vi-VN-HoaiMyNeural",
                }
            ],
        }
        with patch.object(
            gemini_orchestrator, "generate_story_bible", return_value=bible
        ):
            response = self.client.post(
                "/api/ai/story-bible/generate",
                json={
                    "project_id": self.project_id,
                    "selected_concept": concepts["concepts"][0],
                    "creator_answers": {},
                },
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 200, response.text)

        script = {
            "fountain_script": "INT. STUDIO - NIGHT",
            "scenes": [
                {
                    "scene_number": 1,
                    "scene_title": "The signal",
                    "visual_prompt_en": "A quiet studio",
                    "dialogue_vi": "Có ai nghe thấy tôi không?",
                    "estimated_duration": 8,
                }
            ],
        }
        with patch.object(
            gemini_orchestrator, "generate_script_and_scenes", return_value=script
        ):
            response = self.client.post(
                "/api/ai/scripts/generate",
                json={
                    "project_id": self.project_id,
                    "story_bible": bible,
                    "episode_number": 1,
                },
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 200, response.text)

    def test_authentication_and_project_isolation(self) -> None:
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/projects/").status_code, 401)
        self.assertEqual(
            self.client.get("/api/auth/me", headers=self.headers).status_code, 200
        )
        other = self._register_account(
            "other@example.test",
            "email",
            "Other Creator",
            "another-test-password",
        )
        other_headers = {
            "Authorization": f"Bearer {other.json()['access_token']}"
        }
        self.assertEqual(self.client.get("/api/projects/", headers=other_headers).json(), [])
        self.assertEqual(
            self.client.get(
                f"/api/projects/{self.project_id}/analytics", headers=other_headers
            ).status_code,
            404,
        )

    def test_registration_login_and_password_reset_with_email_otp(self) -> None:
        self.client.cookies.clear()
        self.assertEqual(
            self.client.post(
                "/api/auth/register",
                json={
                    "email": "legacy@example.test",
                    "password": "another-test-password",
                    "full_name": "Legacy",
                },
            ).status_code,
            410,
        )
        wrong_code = self.client.post(
            "/api/auth/register/verify",
            json={
                "channel": "email",
                "contact": "new@example.test",
                "otp": "000000",
                "password": "new-test-password",
                "full_name": "New User",
            },
        )
        self.assertEqual(wrong_code.status_code, 400)

        with patch("app.api.auth_routes.send_otp") as send_otp:
            requested = self.client.post(
                "/api/auth/otp/request",
                json={
                    "channel": "email",
                    "contact": "new@example.test",
                    "purpose": "register",
                },
            )
            self.assertEqual(requested.status_code, 200, requested.text)
            code = send_otp.call_args.args[2]
        registered = self.client.post(
            "/api/auth/register/verify",
            json={
                "channel": "email",
                "contact": "new@example.test",
                "otp": code,
                "password": "new-test-password",
                "full_name": "New User",
            },
        )
        self.assertEqual(registered.status_code, 201, registered.text)
        self.assertEqual(registered.json()["user"]["email"], "new@example.test")
        self.assertIsNone(registered.json()["user"]["phone"])

        self.client.cookies.clear()
        login = self.client.post(
            "/api/auth/login",
            json={"identifier": "new@example.test", "password": "new-test-password"},
        )
        self.assertEqual(login.status_code, 200, login.text)

        self.client.cookies.clear()
        with patch("app.api.auth_routes.send_otp") as send_otp:
            requested = self.client.post(
                "/api/auth/otp/request",
                json={
                    "channel": "email",
                    "contact": "new@example.test",
                    "purpose": "password_reset",
                },
            )
            self.assertEqual(requested.status_code, 200, requested.text)
            reset_code = send_otp.call_args.args[2]
        reset = self.client.post(
            "/api/auth/password/reset",
            json={
                "channel": "email",
                "contact": "new@example.test",
                "otp": reset_code,
                "new_password": "updated-test-password",
            },
        )
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"identifier": "new@example.test", "password": "new-test-password"},
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={
                    "identifier": "new@example.test",
                    "password": "updated-test-password",
                },
            ).status_code,
            200,
        )

    def test_phone_registration_and_login(self) -> None:
        self.client.cookies.clear()
        registered = self._register_account(
            "0901234567", "phone", "Phone User", "phone-test-password"
        )
        self.assertEqual(registered.status_code, 201, registered.text)
        self.assertIsNone(registered.json()["user"]["email"])
        self.assertEqual(registered.json()["user"]["phone"], "+84901234567")

        self.client.cookies.clear()
        login = self.client.post(
            "/api/auth/login",
            json={"identifier": "0901234567", "password": "phone-test-password"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["user"]["phone"], "+84901234567")

    def test_google_sign_in_creates_verified_account_and_sets_session(self) -> None:
        self.assertEqual(
            self.client.get("/api/auth/google/config").json(),
            {"configured": False, "client_id": None},
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/google", json={"credential": "google-id-token"}
            ).status_code,
            503,
        )

        settings.GOOGLE_CLIENT_ID = "test-google-client.apps.googleusercontent.com"
        claims = {
            "sub": "google-subject-123",
            "email": "google-user@example.test",
            "email_verified": True,
            "name": "Google User",
        }
        with patch(
            "app.api.auth_routes.id_token.verify_oauth2_token",
            return_value=claims,
        ) as verify_token:
            response = self.client.post(
                "/api/auth/google", json={"credential": "signed-google-id-token"}
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["user"]["email"], claims["email"])
        self.assertIsNone(response.json()["user"]["phone"])
        verify_token.assert_called_once()
        self.assertEqual(verify_token.call_args.args[0], "signed-google-id-token")
        self.assertEqual(
            verify_token.call_args.args[2], settings.GOOGLE_CLIENT_ID
        )
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

        with patch(
            "app.api.auth_routes.id_token.verify_oauth2_token",
            return_value=claims,
        ):
            duplicate = self.client.post(
                "/api/auth/google", json={"credential": "another-google-id-token"}
            )
        self.assertEqual(duplicate.status_code, 200)
        with get_db() as connection:
            user_count = connection.execute(
                "SELECT COUNT(*) FROM users WHERE lower(email) = ?",
                (claims["email"],),
            ).fetchone()[0]
        self.assertEqual(user_count, 1)

    def test_google_sign_in_rejects_unverified_email_and_bad_token(self) -> None:
        settings.GOOGLE_CLIENT_ID = "test-google-client.apps.googleusercontent.com"
        with patch(
            "app.api.auth_routes.id_token.verify_oauth2_token",
            return_value={
                "sub": "unverified-subject",
                "email": "unverified@example.test",
                "email_verified": False,
            },
        ):
            unverified = self.client.post(
                "/api/auth/google", json={"credential": "unverified-token"}
            )
        self.assertEqual(unverified.status_code, 401)

        with patch(
            "app.api.auth_routes.id_token.verify_oauth2_token",
            side_effect=ValueError("invalid signature"),
        ):
            invalid = self.client.post(
                "/api/auth/google", json={"credential": "invalid-token"}
            )
        self.assertEqual(invalid.status_code, 401)

    def test_otp_attempt_and_send_limits(self) -> None:
        contact = "limited@example.test"
        for _ in range(3):
            with patch("app.api.auth_routes.send_otp"):
                response = self.client.post(
                    "/api/auth/otp/request",
                    json={
                        "channel": "email",
                        "contact": contact,
                        "purpose": "register",
                    },
                )
            self.assertEqual(response.status_code, 200)
        limited = self.client.post(
            "/api/auth/otp/request",
            json={
                "channel": "email",
                "contact": contact,
                "purpose": "register",
            },
        )
        self.assertEqual(limited.status_code, 429)

        with get_db() as connection:
            connection.execute(
                """
                UPDATE auth_otps SET expires_at = 0
                WHERE destination = ? AND purpose = 'register'
                """,
                (contact,),
            )
        expired = self.client.post(
            "/api/auth/register/verify",
            json={
                "channel": "email",
                "contact": contact,
                "otp": "123456",
                "password": "long-test-password",
                "full_name": "Limited User",
            },
        )
        self.assertEqual(expired.status_code, 400)

        with patch("app.api.auth_routes.send_otp") as send_otp:
            self.client.post(
                "/api/auth/otp/request",
                json={
                    "channel": "email",
                    "contact": "attempts@example.test",
                    "purpose": "register",
                },
            )
            valid_code = send_otp.call_args.args[2]
        for _ in range(5):
            rejected = self.client.post(
                "/api/auth/register/verify",
                json={
                    "channel": "email",
                    "contact": "attempts@example.test",
                    "otp": "000000" if valid_code != "000000" else "000001",
                    "password": "long-test-password",
                    "full_name": "Attempt User",
                },
            )
            self.assertEqual(rejected.status_code, 400)
        locked = self.client.post(
            "/api/auth/register/verify",
            json={
                "channel": "email",
                "contact": "attempts@example.test",
                "otp": valid_code,
                "password": "long-test-password",
                "full_name": "Attempt User",
            },
        )
        self.assertEqual(locked.status_code, 400)

        with patch(
            "app.api.auth_routes.send_otp",
            side_effect=OTPDeliveryError("SMTP chưa cấu hình."),
        ):
            delivery_failure = self.client.post(
                "/api/auth/otp/request",
                json={
                    "channel": "email",
                    "contact": "delivery@example.test",
                    "purpose": "register",
                },
            )
        self.assertEqual(delivery_failure.status_code, 503)
        self.assertIn("SMTP", delivery_failure.json()["detail"])

    def test_episode_management_and_continuity_context(self) -> None:
        first = self.client.post(
            f"/api/projects/{self.project_id}/episodes",
            json={"title": "Tập mở đầu", "synopsis": "Nhân vật tìm thấy tín hiệu."},
            headers=self.headers,
        )
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["episode_number"], 1)
        second = self.client.post(
            f"/api/projects/{self.project_id}/episodes",
            json={"title": "Tập tiếp nối", "synopsis": "Tìm nguồn tín hiệu."},
            headers=self.headers,
        )
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()["episode_number"], 2)

        updated = self.client.put(
            f"/api/projects/{self.project_id}/episodes/2",
            json={"title": "Tập hai", "synopsis": "Tiếp tục điều tra."},
            headers=self.headers,
        )
        self.assertEqual(updated.status_code, 200)
        self._create_story_and_script()

        script = {
            "fountain_script": "INT. HARBOR - NIGHT",
            "scenes": [
                {
                    "scene_number": 1,
                    "scene_title": "Nguồn tín hiệu",
                    "visual_prompt_en": "Harbor at night",
                    "dialogue_vi": "Tín hiệu đến từ đây.",
                    "estimated_duration": 7,
                }
            ],
        }
        with patch.object(
            gemini_orchestrator,
            "generate_script_and_scenes",
            return_value=script,
        ) as generate:
            response = self.client.post(
                "/api/ai/scripts/generate",
                json={
                    "project_id": self.project_id,
                    "story_bible": {"logline": "A test story."},
                    "episode_number": 2,
                },
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 200, response.text)
        context = generate.call_args.args[0]["_cinai_continuity"]
        self.assertEqual(context["episode"]["title"], "Tập hai")
        self.assertEqual(context["character_memory"][0]["name"], "Ari")
        self.assertEqual(context["previous_episode_scenes"][0]["title"], "The signal")
        self.assertEqual(
            self.client.get(
                f"/api/projects/{self.project_id}/scenes?episode_number=2",
                headers=self.headers,
            ).json()[0]["title"],
            "Nguồn tín hiệu",
        )

    def test_season_management_and_episode_assignment(self) -> None:
        seasons = self.client.get(
            f"/api/projects/{self.project_id}/seasons", headers=self.headers
        )
        self.assertEqual(seasons.status_code, 200, seasons.text)
        self.assertEqual(seasons.json()[0]["season_number"], 1)

        created_season = self.client.post(
            f"/api/projects/{self.project_id}/seasons",
            json={"title": "Mùa hai", "synopsis": "Câu chuyện tiếp nối."},
            headers=self.headers,
        )
        self.assertEqual(created_season.status_code, 201, created_season.text)
        self.assertEqual(created_season.json()["season_number"], 2)

        created_episode = self.client.post(
            f"/api/projects/{self.project_id}/episodes",
            json={
                "title": "Tín hiệu mới",
                "synopsis": "Tập mở đầu mùa hai.",
                "season_number": 2,
            },
            headers=self.headers,
        )
        self.assertEqual(created_episode.status_code, 201, created_episode.text)
        self.assertEqual(created_episode.json()["season_id"], created_season.json()["id"])
        listed_episodes = self.client.get(
            f"/api/projects/{self.project_id}/episodes", headers=self.headers
        ).json()
        self.assertEqual(listed_episodes[0]["season_number"], 2)

        blocked_delete = self.client.delete(
            f"/api/projects/{self.project_id}/seasons/2", headers=self.headers
        )
        self.assertEqual(blocked_delete.status_code, 409)

        renamed = self.client.put(
            f"/api/projects/{self.project_id}/seasons/2",
            json={"title": "Mùa hai sửa", "synopsis": ""},
            headers=self.headers,
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["title"], "Mùa hai sửa")

        missing_season = self.client.post(
            f"/api/projects/{self.project_id}/episodes",
            json={"title": "Sai mùa", "season_number": 3},
            headers=self.headers,
        )
        self.assertEqual(missing_season.status_code, 404)

        registration = self._register_account(
            "other@example.test", "email", "Other Creator", "other-valid-password"
        )
        self.assertEqual(registration.status_code, 201, registration.text)
        other_headers = {}
        forbidden = self.client.get(
            f"/api/projects/{self.project_id}/seasons", headers=other_headers
        )
        self.assertEqual(forbidden.status_code, 404)

    def test_social_oauth_state_and_analytics_sync(self) -> None:
        missing_config = self.client.get(
            f"/api/social/projects/{self.project_id}/youtube/connect",
            headers=self.headers,
            follow_redirects=False,
        )
        self.assertEqual(missing_config.status_code, 503)

        settings.SOCIAL_YOUTUBE_CLIENT_ID = "youtube-test-client"
        settings.SOCIAL_YOUTUBE_CLIENT_SECRET = "youtube-test-secret"
        redirect = self.client.get(
            f"/api/social/projects/{self.project_id}/youtube/connect",
            headers=self.headers,
            follow_redirects=False,
        )
        self.assertEqual(redirect.status_code, 302)
        authorization = urllib.parse.urlparse(redirect.headers["location"])
        state = urllib.parse.parse_qs(authorization.query)["state"][0]
        with get_db() as connection:
            oauth_state = connection.execute(
                "SELECT project_id, user_id, platform FROM social_oauth_states WHERE state = ?",
                (state,),
            ).fetchone()
        self.assertEqual(oauth_state["project_id"], self.project_id)
        self.assertEqual(oauth_state["platform"], "youtube")

        with (
            patch.object(
                social_routes,
                "_exchange_code",
                return_value={
                    "access_token": "plain-access-token",
                    "refresh_token": "plain-refresh-token",
                    "expires_in": 3600,
                },
            ),
            patch.object(
                social_routes,
                "_account_for_platform",
                return_value=("channel-1", "Test Channel", "page-token"),
            ),
        ):
            callback = self.client.get(
                f"/api/social/youtube/callback?state={state}&code=auth-code",
                follow_redirects=False,
            )
        self.assertEqual(callback.status_code, 303)
        self.assertIn("social=connected", callback.headers["location"])
        with get_db() as connection:
            linked = connection.execute(
                "SELECT * FROM social_connections WHERE project_id = ? AND platform = 'youtube'",
                (self.project_id,),
            ).fetchone()
            remaining_states = connection.execute(
                "SELECT COUNT(*) FROM social_oauth_states WHERE state = ?", (state,)
            ).fetchone()[0]
        self.assertNotEqual(linked["access_token"], "page-token")
        self.assertEqual(
            social_routes._decrypt_token(linked["access_token"]), "page-token"
        )
        self.assertEqual(remaining_states, 0)

        metrics = {
            "external_content_id": "video-1",
            "view_count": 1234,
            "watch_time_avg_sec": 28.5,
            "like_count": 41,
            "comment_count": 7,
            "share_count": 3,
            "unique_viewers": 0,
            "retention_rate": 0,
        }
        with (
            patch.object(
                social_routes, "_refresh_token", return_value=("access-token", None)
            ),
            patch.object(social_routes, "_youtube_rows", return_value=[metrics]) as sync,
        ):
            result = self.client.post(
                f"/api/social/projects/{self.project_id}/youtube/sync?days=14",
                headers=self.headers,
            )
            repeated = self.client.post(
                f"/api/social/projects/{self.project_id}/youtube/sync?days=14",
                headers=self.headers,
            )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["synced"], 1)
        self.assertEqual(result.json()["totals"]["view_count"], 1234)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(sync.call_count, 2)
        sync.assert_called_with("access-token", 14)

        with get_db() as connection:
            analytics = connection.execute(
                """
                SELECT platform, external_content_id, view_count
                FROM analytics WHERE project_id = ? AND platform = 'youtube'
                """,
                (self.project_id,),
            ).fetchall()
        self.assertEqual(len(analytics), 1)
        self.assertEqual(analytics[0]["external_content_id"], "video-1")
        self.assertEqual(analytics[0]["view_count"], 1234)

    def test_generation_restore_and_analytics_csv_import(self) -> None:
        self._create_story_and_script()
        generations = self.client.get(
            f"/api/projects/{self.project_id}/generations?limit=50",
            headers=self.headers,
        ).json()
        script_generation = next(item for item in generations if item["step"] == "script")
        restored = self.client.post(
            f"/api/projects/{self.project_id}/generations/{script_generation['id']}/restore",
            headers=self.headers,
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["step"], "script")
        self.assertEqual(restored.json()["episode_number"], 1)
        scenes = self.client.get(
            f"/api/projects/{self.project_id}/scenes?episode_number=1",
            headers=self.headers,
        ).json()
        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0]["title"], "The signal")
        subtitles = self.client.get(
            f"/api/media/projects/{self.project_id}/episodes/1/subtitles.srt",
            headers=self.headers,
        )
        self.assertEqual(subtitles.status_code, 200, subtitles.text)
        self.assertEqual(subtitles.text.count("Có ai nghe thấy tôi không?"), 1)

        csv_content = (
            "id,project_id,view_count,unique_viewers,watch_time_avg_sec,"
            "retention_rate,like_count,comment_count,share_count,recorded_at\r\n"
            f",999,1200,900,23.5,68.2,45,6,9,2026-11-06T10:00:00\r\n"
            f",999,1500,1100,25,70,51,7,11,2026-11-07T10:00:00\r\n"
        )
        imported = self.client.post(
            f"/api/projects/{self.project_id}/analytics/import-csv",
            files={"file": ("analytics.csv", BytesIO(csv_content.encode()), "text/csv")},
            headers=self.headers,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["imported"], 2)
        analytics = self.client.get(
            f"/api/projects/{self.project_id}/analytics", headers=self.headers
        ).json()["data"]
        self.assertEqual(len(analytics["history"]), 2)
        self.assertEqual(analytics["latest"]["view_count"], 1500)

        invalid = self.client.post(
            f"/api/projects/{self.project_id}/analytics/import-csv",
            files={"file": ("bad.csv", BytesIO(b"wrong,columns\n1,2\n"), "text/csv")},
            headers=self.headers,
        )
        self.assertEqual(invalid.status_code, 422)

    def test_story_bible_restore_updates_existing_world_and_characters(self) -> None:
        story_bible = {
            "logline": "A test story.",
            "theme": "Trust",
            "world_bible": {
                "world_name": "Signal City",
                "era_setting": "2088",
                "rules_and_lore": ["Signals are rare."],
            },
            "character_bible": [
                {
                    "name": "Ari",
                    "role": "protagonist",
                    "personality": "Curious",
                }
            ],
        }
        with patch.object(
            gemini_orchestrator, "generate_story_bible", return_value=story_bible
        ):
            generated = self.client.post(
                "/api/ai/story-bible/generate",
                json={
                    "project_id": self.project_id,
                    "selected_concept": {"title": "Test concept"},
                },
                headers=self.headers,
            )
        self.assertEqual(generated.status_code, 200, generated.text)
        history = self.client.get(
            f"/api/projects/{self.project_id}/generations?step=story_bible",
            headers=self.headers,
        ).json()
        restored = self.client.post(
            f"/api/projects/{self.project_id}/generations/{history[0]['id']}/restore",
            headers=self.headers,
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        with get_db() as connection:
            world_count = connection.execute(
                "SELECT COUNT(*) FROM worlds WHERE project_id = ? AND name = ?",
                (self.project_id, "Signal City"),
            ).fetchone()[0]
            character_count = connection.execute(
                "SELECT COUNT(*) FROM characters WHERE project_id = ? AND name = ?",
                (self.project_id, "Ari"),
            ).fetchone()[0]
            story_bible_count = connection.execute(
                "SELECT COUNT(*) FROM story_bibles WHERE project_id = ?",
                (self.project_id,),
            ).fetchone()[0]
        self.assertEqual(world_count, 1)
        self.assertEqual(character_count, 1)
        self.assertEqual(story_bible_count, 2)

    def test_video_render_uses_selected_episode(self) -> None:
        with (
            patch("app.api.media_routes._find_ffmpeg", return_value="ffmpeg"),
            patch(
                "app.api.media_routes._approved_scenes_for_project",
                return_value=[{"id": 1}],
            ) as select_scenes,
            patch("app.api.media_routes._render_video") as render_video,
        ):
            response = self.client.post(
                f"/api/media/projects/{self.project_id}/render?episode_number=2",
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 202, response.text)
        select_scenes.assert_called_once_with(self.project_id, 2)
        render_video.assert_called_once()
        with get_db() as connection:
            render = connection.execute(
                "SELECT episode_number, status FROM video_renders WHERE id = ?",
                (response.json()["render_id"],),
            ).fetchone()
        self.assertEqual(render["episode_number"], 2)
        self.assertEqual(render["status"], "rendering")
        with get_db() as connection:
            connection.execute(
                "UPDATE video_renders SET status = 'failed' WHERE id = ?",
                (response.json()["render_id"],),
            )
        with (
            patch("app.api.media_routes._find_ffmpeg", return_value="ffmpeg"),
            patch(
                "app.api.media_routes._approved_scenes_for_project",
                return_value=[{"id": 1}],
            ) as select_scenes,
            patch("app.api.media_routes._render_video"),
        ):
            retried = self.client.post(
                f"/api/media/projects/{self.project_id}/renders/{response.json()['render_id']}/retry",
                headers=self.headers,
            )
        self.assertEqual(retried.status_code, 202, retried.text)
        select_scenes.assert_called_once_with(self.project_id, 2)
        with get_db() as connection:
            retry_render = connection.execute(
                "SELECT episode_number FROM video_renders WHERE id = ?",
                (retried.json()["render_id"],),
            ).fetchone()
        self.assertEqual(retry_render["episode_number"], 2)

    def test_media_retry_status_and_subtitle_download(self) -> None:
        self._create_story_and_script()
        with get_db() as connection:
            scene = connection.execute(
                "SELECT id FROM scenes WHERE project_id = ? ORDER BY id LIMIT 1",
                (self.project_id,),
            ).fetchone()
            cursor = connection.execute(
                """
                INSERT INTO assets
                    (project_id, scene_id, name, asset_type, status, error_message, request_json)
                VALUES (?, ?, 'Ảnh cảnh lỗi', 'visual', 'failed', 'Provider lỗi', ?)
                """,
                (
                    self.project_id,
                    scene["id"],
                    json.dumps({"prompt": "A detailed cinematic scene"}, ensure_ascii=False),
                ),
            )
            failed_asset_id = cursor.lastrowid

        settings.STABILITY_API_KEY = "test-stability-key"
        with patch("app.api.media_routes._generate_image") as generate_image:
            retry = self.client.post(
                f"/api/media/assets/{failed_asset_id}/retry",
                headers=self.headers,
            )
        self.assertEqual(retry.status_code, 202, retry.text)
        self.assertEqual(retry.json()["status"], "generating")
        generate_image.assert_called_once()

        subtitles = self.client.get(
            f"/api/media/projects/{self.project_id}/episodes/1/subtitles.srt",
            headers=self.headers,
        )
        self.assertEqual(subtitles.status_code, 200)
        self.assertIn("Có ai nghe thấy tôi không?", subtitles.text)
        capabilities = self.client.get(
            "/api/media/capabilities", headers=self.headers
        )
        self.assertEqual(capabilities.status_code, 200)
        self.assertEqual(capabilities.json()["image_provider"], "configured")

    def test_grok_requires_key_and_selected_provider_is_used(self) -> None:
        payload = {
            "project_id": self.project_id,
            "raw_idea": "A story about a lost signal",
            "genre": "Sci-Fi",
            "ai_provider": "grok",
        }
        missing_key = self.client.post(
            "/api/ai/ideas/generate", json=payload, headers=self.headers
        )
        self.assertEqual(missing_key.status_code, 503)
        self.assertIn("XAI_API_KEY", missing_key.json()["detail"])

        settings.XAI_API_KEY = "unit-test-xai-key"
        expected = {"concepts": [{"title": "Grok concept", "logline": "Test."}]}
        with patch.object(
            grok_orchestrator, "generate_concepts", return_value=expected
        ) as generate:
            response = self.client.post(
                "/api/ai/ideas/generate", json=payload, headers=self.headers
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), expected)
        generate.assert_called_once_with(payload["raw_idea"], payload["genre"])

    def test_logout_clears_cookie_and_unconfigured_image_provider_is_explicit(self) -> None:
        logout = self.client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        response = self.client.post(
            "/api/media/images",
            json={
                "project_id": self.project_id,
                "scene_id": 1,
                "prompt": "A cinematic landscape for the scene",
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 503)

    def test_ai_outputs_persist_and_regeneration_keeps_previous_versions(self) -> None:
        self._create_story_and_script()
        scenes = self.client.get(
            f"/api/projects/{self.project_id}/scenes", headers=self.headers
        )
        self.assertEqual(scenes.status_code, 200, scenes.text)
        self.assertEqual(scenes.json()[0]["title"], "The signal")

        replacement = {
            "fountain_script": "INT. HARBOR - NIGHT",
            "scenes": [
                {
                    "scene_number": 1,
                    "scene_title": "At the harbor",
                    "visual_prompt_en": "A dark harbor",
                    "dialogue_vi": "Tín hiệu ở kia.",
                    "estimated_duration": 10,
                }
            ],
        }
        with patch.object(
            gemini_orchestrator,
            "generate_script_and_scenes",
            return_value=replacement,
        ):
            regenerated = self.client.post(
                "/api/ai/scripts/generate",
                json={
                    "project_id": self.project_id,
                    "story_bible": {"logline": "A test story."},
                    "episode_number": 1,
                },
                headers=self.headers,
            )
        self.assertEqual(regenerated.status_code, 200, regenerated.text)
        current_scenes = self.client.get(
            f"/api/projects/{self.project_id}/scenes", headers=self.headers
        ).json()
        self.assertEqual([scene["title"] for scene in current_scenes], ["At the harbor"])

        connection = sqlite3.connect(settings.DATABASE_PATH)
        try:
            scene_versions = connection.execute(
                "SELECT COUNT(*) FROM scenes WHERE project_id = ?",
                (self.project_id,),
            ).fetchone()[0]
            generation_count = connection.execute(
                "SELECT COUNT(*) FROM ai_generations WHERE project_id = ?",
                (self.project_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(scene_versions, 2)
        self.assertEqual(generation_count, 4)
        self.assertEqual(
            self.client.get(
                f"/api/projects/{self.project_id}/characters", headers=self.headers
            ).json()[0]["name"],
            "Ari",
        )

    def test_ai_failure_does_not_overwrite_saved_scenes(self) -> None:
        self._create_story_and_script()
        with patch.object(
            gemini_orchestrator,
            "generate_script_and_scenes",
            side_effect=RuntimeError("provider unavailable"),
        ):
            response = self.client.post(
                "/api/ai/scripts/generate",
                json={
                    "project_id": self.project_id,
                    "story_bible": {},
                    "episode_number": 1,
                },
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 502)
        scenes = self.client.get(
            f"/api/projects/{self.project_id}/scenes", headers=self.headers
        ).json()
        self.assertEqual(scenes[0]["title"], "The signal")

    def test_analytics_and_gemini_recommendations_persist(self) -> None:
        self.client.post(
            f"/api/projects/{self.project_id}/analytics",
            json={
                "view_count": 250,
                "unique_viewers": 200,
                "watch_time_avg_sec": 32.5,
                "retention_rate": 60,
                "like_count": 14,
                "comment_count": 3,
                "share_count": 2,
            },
            headers=self.headers,
        )
        recommendation = {
            "recommendations": [
                {"title": "Open with action", "description": "Use a shorter hook."}
            ]
        }
        with patch.object(
            gemini_orchestrator,
            "generate_analytics_recommendations",
            return_value=recommendation,
        ):
            response = self.client.post(
                f"/api/projects/{self.project_id}/recommendations",
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 200, response.text)
        saved = self.client.get(
            f"/api/projects/{self.project_id}/analytics", headers=self.headers
        ).json()["data"]
        self.assertEqual(saved["latest"]["view_count"], 250)
        self.assertEqual(saved["ai_recommendations"][0]["title"], "Open with action")


class AdditiveMigrationTests(unittest.TestCase):
    def test_existing_sqlite_rows_survive_schema_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = settings.DATABASE_PATH
            settings.DATABASE_PATH = Path(temp_dir) / "legacy.sqlite"
            try:
                connection = sqlite3.connect(settings.DATABASE_PATH)
                try:
                    connection.executescript(
                        """
                        CREATE TABLE users (
                            id INTEGER PRIMARY KEY, email TEXT, hashed_password TEXT,
                            full_name TEXT, role TEXT, created_at TEXT
                        );
                        CREATE TABLE projects (
                            id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT,
                            description TEXT, genre TEXT, status TEXT, created_at TEXT
                        );
                        CREATE TABLE video_renders (
                            id INTEGER PRIMARY KEY, project_id INTEGER,
                            status TEXT, file_url TEXT, created_at TEXT,
                            updated_at TEXT
                        );
                        CREATE TABLE story_bibles (
                            id INTEGER PRIMARY KEY, project_id INTEGER, logline TEXT,
                            theme TEXT, world_setting TEXT, character_profiles TEXT,
                            data_json TEXT, created_at TEXT
                        );
                        CREATE TABLE scenes (
                            id INTEGER PRIMARY KEY, project_id INTEGER,
                            scene_number INTEGER, title TEXT, visual_prompt TEXT,
                            dialogue TEXT, created_at TEXT
                        );
                        INSERT INTO users VALUES (1, 'legacy@example.test', 'hash', 'Legacy', 'creator', '2025-01-01');
                        INSERT INTO projects VALUES (7, 1, 'Legacy project', '', 'Drama', 'draft', '2025-01-01');
                        INSERT INTO video_renders VALUES (11, 7, 'failed', NULL, '2025-01-01', '2025-01-01');
                        INSERT INTO scenes VALUES (9, 7, 1, 'Legacy scene', 'prompt', 'dialogue', '2025-01-01');
                        """
                    )
                finally:
                    connection.close()
                initialize_database()
                connection = sqlite3.connect(settings.DATABASE_PATH)
                try:
                    project = connection.execute(
                        "SELECT title FROM projects WHERE id = 7"
                    ).fetchone()
                    scene = connection.execute(
                        "SELECT title FROM scenes WHERE id = 9"
                    ).fetchone()
                    render = connection.execute(
                        "SELECT status, episode_number FROM video_renders WHERE id = 11"
                    ).fetchone()
                    tables = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    }
                finally:
                    connection.close()
                self.assertEqual(project[0], "Legacy project")
                self.assertEqual(scene[0], "Legacy scene")
                self.assertEqual(render[0], "failed")
                self.assertIsNone(render[1])
                self.assertIn("ai_generations", tables)
                self.assertIn("video_renders", tables)
            finally:
                settings.DATABASE_PATH = original_path


if __name__ == "__main__":
    unittest.main()
