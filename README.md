# CINAI

CINAI is a Vietnamese AI-assisted film-writing studio. `index.html` serves the
landing page and `studio.html` is the canonical Studio interface. FastAPI serves
both pages and the API. Local development defaults to SQLite; Docker Compose
uses PostgreSQL and persistent local media storage.

## Run locally

```powershell
Set-Location .\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Configure only the providers you intend to use in backend\.env.
python -m uvicorn app.main:app --reload --reload-include .env --port 8000
```

Open <http://127.0.0.1:8000/> for the landing page, <http://127.0.0.1:8000/studio>
or <http://127.0.0.1:8000/studio.html> for the standalone Studio, and
<http://127.0.0.1:8000/docs> for the API reference. Landing-page buttons open
the same `studio.html` inside an iframe at `/#studio`; changing the hash while
the landing page is already open loads Studio without requiring a refresh. The
FastAPI app serves both HTML files; keep it running on port 8000 for login and
other API requests.

## Provider configuration

- AI text: configure `GEMINI_API_KEY`; `XAI_API_KEY` enables Grok.
- Sign in with Google: configure `GOOGLE_CLIENT_ID` for a Google OAuth Web client
  and register the website origin in Google Cloud Console.
- Email OTP: configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM_EMAIL`, and SMTP
  credentials when required.
- SMS OTP: configure `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and
  `TWILIO_FROM_NUMBER`.
- Image generation: configure `STABILITY_API_KEY`.
- Speech: install `edge-tts` from the backend requirements.
- Video: install FFmpeg or use the provided container image.

Do not commit `backend/.env` or put provider secrets in frontend files.

## Run with Docker Compose

Create `backend/.env` from `backend/.env.example`, set a persistent random
`SECRET_KEY`, and configure providers as needed. Docker Compose also needs a root
`.env` file with `POSTGRES_DB`, `POSTGRES_USER`, and a strong
`POSTGRES_PASSWORD`. Create it from the example and replace the sample password
with a generated URL-safe value:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -c "import secrets; print(secrets.token_hex(32))"
```

Keep both `.env` files private; they are ignored by Git. Then run from the
project root:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f cinai
```

The service is available at <http://127.0.0.1:8000/>. Docker runs PostgreSQL
17 for application data and persists database files in the `postgres_data`
volume. Generated media and the previous SQLite database remain in the
`cinai_data` volume. Back up both volumes before upgrades or deployments.

Local development still defaults to SQLite. Docker Compose overrides
`DATABASE_URL` with PostgreSQL. To copy an existing SQLite database into an
empty PostgreSQL database, start the services first and run:

```powershell
docker compose exec -T cinai python scripts/migrate_sqlite_to_postgres.py --sqlite-path /data/cinai.db
```

The migration stops if any destination table already contains rows; it does not
delete or modify the SQLite source. Confirm that the SQLite file is the one
containing your existing data before running the command. The first Compose
startup creates an empty PostgreSQL database; the migration command is only
needed when you have existing SQLite data to preserve.

## Social analytics

The Studio can connect YouTube, TikTok, Facebook Pages, and Instagram
Business/Creator accounts. Configure the corresponding client IDs/secrets in
`backend/.env`, set `SOCIAL_OAUTH_BASE_URL` to the public site origin, and
register these exact callback URLs with each OAuth provider:

- `{SOCIAL_OAUTH_BASE_URL}/api/social/youtube/callback`
- `{SOCIAL_OAUTH_BASE_URL}/api/social/tiktok/callback`
- `{SOCIAL_OAUTH_BASE_URL}/api/social/facebook/callback`
- `{SOCIAL_OAUTH_BASE_URL}/api/social/instagram/callback`

The provider applications must be approved for the required OAuth scopes and
account types. Meta insights are limited to eligible Facebook Pages and linked
Instagram Business/Creator accounts; available metrics vary by provider and
permissions. Keep the same persistent `SECRET_KEY` after connecting accounts:
it is used to encrypt stored social tokens. Real provider synchronization
requires valid credentials, registered callbacks, and access granted by each
provider; the automated tests use mocked provider responses.

## Tests

```powershell
Set-Location .\backend
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s .\tests -v
```

See [PROJECT_GUIDE.md](./PROJECT_GUIDE.md) for product scope, workflow, and
remaining implementation roadmap. [Use cases and ERD](./docs/USE_CASES_AND_ERD.md)
document the current logical data model and creator workflows.
