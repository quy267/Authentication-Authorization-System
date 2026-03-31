# Authentication & Authorization System

A production-ready authentication and authorization system built with FastAPI, MongoDB, and Redis. Implements JWT-based auth, role-based access control (RBAC), OAuth2 flows, email verification, account lockout protection, and session revocation.

**Status:** v0.2.0 (28 security fixes, 96% test coverage, audit logging)

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Web Framework | FastAPI | 0.115.12 |
| ASGI Server | Uvicorn | 0.34.2 |
| Database | MongoDB + Beanie ODM | 7 / 1.29.0 |
| Cache/Sessions | Redis | 7 |
| Auth | JWT (HS256) + bcrypt + AuthLib | 2.10.1 / 1.7.4 / 1.4.1 |
| Email | aiosmtplib | 3.0.2 |
| Rate Limiting | slowapi | 0.1.9 |
| Validation | Pydantic | 2.11.1 |
| Testing | pytest + testcontainers | 8.3.5 / 4.10.0 |
| Container | Docker + docker-compose | - |

## Quick Start

### Docker (Recommended)

> **Note:** Docker BuildKit has no DNS access on some machines. Use the steps below which
> build the image with host networking and run services with `network_mode: host`.

```bash
# 1. Create .env from the template below (see Environment Variables section)
cp .env.example .env   # or create .env manually

# 2. Build the app image (required once; repeat after code changes)
DOCKER_BUILDKIT=0 docker build --network=host -t auth-app .

# 3. Start all services (MongoDB, Redis, app)
docker compose up -d

# 4. Verify
curl http://localhost:8000/health
# → {"status":"ok"}
```

**Logs / status:**
```bash
docker compose ps
docker compose logs app -f
```

**Stop everything:**
```bash
docker compose down
```

### Manual Setup

```bash
# Create venv
python3.11 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Start MongoDB & Redis separately
# Then run app:
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints Summary

### Authentication (7 endpoints)
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/auth/register` | Create user account | No |
| POST | `/auth/login` | Get access + refresh tokens | No |
| POST | `/auth/logout` | Blacklist current JWT | Bearer |
| POST | `/auth/refresh` | Get new access token | Bearer (refresh) |
| POST | `/auth/verify-email` | Activate account via token | No |
| POST | `/auth/forgot-password` | Send password reset email | No |
| POST | `/auth/reset-password` | Update password via token | No |

### Roles (4 endpoints - Admin only)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/roles` | Create role |
| GET | `/roles` | List all roles |
| PUT | `/roles/{id}` | Update role |
| DELETE | `/roles/{id}` | Delete role |

### OAuth2 (5 endpoints)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/oauth/clients` | Register OAuth2 client |
| GET | `/oauth/clients` | List registered clients |
| GET | `/oauth/authorize` | Authorization code endpoint |
| POST | `/oauth/token` | Token endpoint (3 grant types) |
| POST | `/oauth/revoke` | Revoke access token |

### Users (3 endpoints)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/users` | List users (admin) |
| POST | `/users/{id}/roles` | Assign roles to user |
| DELETE | `/users/{id}/sessions` | Revoke all user sessions |

### System (1 endpoint)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |

## Environment Variables

See `.env.example`:

```bash
# Database
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=auth_db

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT — REQUIRED, must be ≥32 chars. App will NOT start without it.
# Generate: openssl rand -hex 32
JWT_SECRET_KEY=           # ← REQUIRED (no default — pydantic fails on missing)
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Email
SMTP_HOST=localhost
SMTP_PORT=587
SMTP_USER=your-email@example.com
SMTP_PASSWORD=your-password
EMAIL_FROM=noreply@example.com

# Security
LOCKOUT_THRESHOLD=5              # Failed login attempts
LOCKOUT_DURATION_MINUTES=15      # How long to lock account

# CORS (optional — empty means no CORS middleware)
CORS_ORIGINS=                    # Comma-separated origins, e.g. https://app.example.com,https://admin.example.com
```

## Testing

```bash
# Run all tests with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py -v

# Run with live logging
pytest tests/test_integration.py -v -s
```

Test suite:
- **Unit tests:** Core functions (security, config, models)
- **Integration tests:** Full workflows (auth flows, RBAC, OAuth2)
- **E2E tests:** Real database + email via testcontainers
- **Coverage:** 96% of app code (103 tests)

## Project Structure

```
.
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── docker-compose.yml           # Dev environment (MongoDB, Redis, App)
├── Dockerfile                   # Multi-stage build
├── .env.example                 # Environment template
├── pytest.ini                   # Test configuration
├── app/                         # Main application (30 Python files)
│   ├── main.py                  # App factory, lifespan, health endpoint
│   ├── core/
│   │   ├── config.py            # Pydantic settings (.env loading, JWT key validator)
│   │   ├── security.py          # JWT + bcrypt utilities
│   │   ├── database.py          # MongoDB + Redis init/close
│   │   └── limiter.py           # Shared SlowAPI Limiter instance
│   ├── models/                  # Beanie documents (4 files)
│   │   ├── user.py              # User (email, roles, lockout, tokens)
│   │   ├── role.py              # Role (name, permissions)
│   │   ├── oauth2_client.py     # OAuth2 client registration
│   │   └── oauth2_token.py      # Auth codes + access tokens (TTL indexes)
│   ├── schemas/                 # Pydantic request/response (4 files)
│   │   ├── user.py
│   │   ├── role.py
│   │   ├── oauth2.py
│   │   └── auth.py
│   ├── services/                # Business logic (6 files)
│   │   ├── auth_service.py      # Register, login, refresh, email flows
│   │   ├── oauth2_service.py    # OAuth2 authorization code, PKCE, tokens
│   │   ├── lockout_service.py   # Failed login lockout (Redis, fixed window TTL)
│   │   ├── email_service.py     # Async SMTP email
│   │   ├── role_service.py      # Role CRUD operations
│   │   └── user_service.py      # User operations (list, roles, session revocation)
│   └── api/                     # HTTP routes (5 files)
│       ├── deps.py              # Dependency injection (N+1 fix in require_permission)
│       ├── auth_routes.py       # /auth/* endpoints (with rate limiting)
│       ├── role_routes.py       # /roles/* endpoints (thin handlers, delegates to role_service)
│       ├── oauth2_routes.py     # /oauth/* endpoints (with rate limiting)
│       └── user_routes.py       # /users/* endpoints (thin handlers, delegates to user_service)
├── tests/                       # Test suite (13 files, 1,496 LOC)
│   ├── conftest.py              # Fixtures: Docker containers, async client
│   ├── test_auth.py             # Auth flow tests (171 lines)
│   ├── test_rbac.py             # Role + permission tests (138 lines)
│   ├── test_oauth2.py           # OAuth2 flow tests (392 lines)
│   ├── test_account_security.py # Lockout + email tests (104 lines)
│   ├── test_email_flows.py      # Verification + reset (186 lines)
│   ├── test_integration.py      # Full workflows (173 lines)
│   └── __init__.py
└── docs/                        # Documentation (this file + guides)
    ├── project-overview-pdr.md  # Goals, requirements, success metrics
    ├── codebase-summary.md      # File-by-file breakdown, patterns
    ├── code-standards.md        # Python conventions, error handling
    ├── system-architecture.md   # Flows, component diagrams
    ├── project-roadmap.md       # Phases, completed work, future tasks
    ├── deployment-guide.md      # Docker, manual setup, production checklist
    └── design-guidelines.md     # API design, security principles
```

## Key Features

- **JWT Authentication:** Unique JTI per token, Redis blacklist with TTL, refresh token rotation, required secret key (no default)
- **RBAC:** Roles + permissions model, admin-only endpoints, default roles protected, optimized $in queries, idempotent seeding
- **OAuth2:** RFC 6749 auth code + client credentials, RFC 7636 PKCE (S256 with `hmac.compare_digest`), RFC 7009 revocation (client auth required), atomic code exchange, auth code reuse revokes all tokens (RFC 6749 §4.1.2), public clients blocked from client_credentials
- **Email Verification:** 1-hour expiring tokens, rate-limited (3/hour), enumeration prevention (generic error messages)
- **Password Reset:** Secure 30-minute tokens, verification workflow, bcrypt 72-byte validation (UTF-8 byte length)
- **Account Lockout:** Email-hash keyed (works for non-existent users), checked before user lookup, 5 failures = 15-min lockout via Redis (fixed window TTL)
- **Rate Limiting:** Shared limiter instance, /auth endpoints (10/min), /auth/refresh (20/min), /oauth/token (20/min), /forgot-password (5/min), /verify-email (10/min), /reset-password (10/min)
- **Login Security:** Timing oracle prevention (dummy bcrypt on missing users), is_active checked before password verification
- **MongoDB Indexes:** TTL indexes on OAuth2 auth codes, sparse indexes on verification tokens
- **Session Revocation:** Blacklist via Redis, per-user session tracking, `revoked_at:` keys with TTL
- **Audit Logging:** Structured JSON to stdout for login, logout, password_reset, sessions_revoked, roles_changed
- **CORS:** Configurable via `CORS_ORIGINS` env var (empty = disabled)
- **Async:** 100% async (asyncio, motor with `tz_aware=True`, aiosmtplib, hiredis)
- **Docker:** Non-root container (appuser), multi-stage build
- **Security:** bcrypt hashing, timing-safe comparisons, HTTPS-ready, SQL injection-proof (ODM)

## Security Checklist

- [ ] Set `JWT_SECRET_KEY` in .env — **REQUIRED** (app won't start without it). Generate: `openssl rand -hex 32`
- [ ] Configure SMTP credentials (email verification, password reset)
- [ ] Use HTTPS in production (Uvicorn behind reverse proxy)
- [ ] Set `CORS_ORIGINS` to restrict allowed origins (empty = no CORS middleware)
- [ ] Monitor Redis/MongoDB access (firewall rules)
- [ ] Rotate JWT keys periodically
- [ ] Enable database backups (MongoDB)
- [ ] Set strong password policies in frontend (note: bcrypt truncates at 72 bytes)
- [ ] Use environment-specific .env files
- [ ] Review rate limiting thresholds for your load
- [ ] Verify Docker runs as non-root (`appuser`)
- [ ] Review audit logs (structured JSON to stdout) for security events

## Contributing

1. Read `docs/code-standards.md` for Python conventions
2. Read `docs/project-roadmap.md` to understand completed work
3. Ensure all tests pass: `pytest --cov=app`
4. Follow commit message format: `feat:`, `fix:`, `docs:`, `refactor:`
5. Update relevant docs when adding features

## Development

**Run tests locally:**
```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

**Run linter (if added):**
```bash
ruff check app/
```

**Format code (if added):**
```bash
black app/ tests/
```

**Check type hints (if added):**
```bash
mypy app/
```

## License

Apache 2.0

## Documentation

See `docs/` directory for:
- System architecture and data flows
- API integration guide
- Deployment instructions
- Code standards and patterns
- Development roadmap and changelog
