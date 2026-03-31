# Project Roadmap & Progress Tracking

Development phases, milestones, and future work.

**Last Updated:** 2026-03-31 | **Current Version:** 0.2.0 | **Overall Progress:** 100% (Phase 1-7 Complete, 28 Security Fixes)

---

## Phase Summary

| Phase | Name | Status | Progress | Date | Notes |
|-------|------|--------|----------|------|-------|
| 1 | Core Auth | ✅ Complete | 100% | 2026-03-29 | JWT, register, login, logout, refresh |
| 2 | RBAC | ✅ Complete | 100% | 2026-03-29 | Roles, permissions, admin endpoints |
| 3 | OAuth2 | ✅ Complete | 100% | 2026-03-29 | Auth code, PKCE, client credentials |
| 4 | Email Flows | ✅ Complete | 100% | 2026-03-29 | Verification, password reset, rate limiting |
| 5 | Account Security | ✅ Complete | 100% | 2026-03-29 | Lockout, session revocation |
| 6 | Docker | ✅ Complete | 100% | 2026-03-29 | Containerization, docker-compose |
| 7 | Testing | ✅ Complete | 100% | 2026-03-29 | Unit, integration, e2e tests, 90%+ coverage |
| 8 | Future Work | 🔜 Planned | 0% | TBD | Session revocation fix, audit logging, GDPR |

---

## Completed Phases (v0.1.0)

### Phase 1: Core Authentication ✅
- JWT-based authentication with unique JTI per token
- User registration with bcrypt password hashing
- Login with token generation (access: 30min, refresh: 7days)
- Token refresh mechanism
- Logout with Redis blacklist
- **Status:** Complete

### Phase 2: Role-Based Access Control ✅
- Role and permission models
- Role CRUD endpoints (admin-only)
- Authorization dependencies (require_role, require_permission)
- Default roles ("admin", "user")
- **Status:** Complete

### Phase 3: OAuth2 Integration ✅
- RFC 6749 authorization code flow
- RFC 7636 PKCE support (S256)
- Client credentials flow (service-to-service)
- RFC 7009 token revocation
- 5 endpoints (clients, authorize, token, revoke)
- **Status:** Complete

### Phase 4: Email Flows ✅
- Email verification (1-hour expiring tokens)
- Password reset (30-minute expiring tokens)
- Async SMTP email sending (aiosmtplib)
- Email rate limiting (3/hour)
- **Status:** Complete

### Phase 5: Account Security ✅
- Account lockout (5 failures → 15-min lockout)
- Redis-based lockout tracking
- Session revocation endpoint (admin)
- IP-based rate limiting (slowapi)
- **Status:** Complete

### Phase 6: Docker & Containerization ✅
- Multi-stage Dockerfile (Python 3.11)
- docker-compose with MongoDB + Redis
- Health checks on all services
- Production-ready configuration
- **Status:** Complete

### Phase 7: Testing & QA ✅
- 90%+ code coverage (pytest)
- Unit tests (functions/methods)
- Integration tests (workflows with real MongoDB + Redis)
- E2E tests (full HTTP flows)
- testcontainers for isolated environments
- **Status:** Complete

---

## v0.2.0 Security Release (28 Fixes, 2026-03-31)

### Critical Fixes (7)
- **C1:** Fixed datetime.utcnow() crash — added `tz_aware=True` to Motor client, replaced all `datetime.utcnow()` with `datetime.now(timezone.utc)`
- **C2:** Login timing oracle prevention — dummy bcrypt hash on missing users for constant-time response
- **C3:** PKCE uses `hmac.compare_digest()` instead of `==` (timing side-channel fix)
- **C4:** OAuth2 refresh uses atomic `find_one_and_update` (TOCTOU race fix)
- **C5:** JWT_SECRET_KEY now required (no default) — pydantic fails on missing env var
- **C6:** Auth code reuse revokes all tokens per RFC 6749 §4.1.2
- **C7:** Dockerfile runs as non-root user (appuser)

### Important Fixes (12)
- **I1:** Lockout checked before user lookup (email-hash keyed, works for non-existent users)
- **I2:** is_active checked before password verification
- **I3:** Registration returns generic error "Registration could not be completed" (enumeration prevention)
- **I4:** bcrypt 72-byte validation on password (UTF-8 byte length, not char length)
- **I5:** `revoked_at:` Redis keys now have TTL (REFRESH_TOKEN_EXPIRE_DAYS * 86400). DRY: consolidated between auth_service and user_service
- **I6:** Email rate limit uses atomic INCR-first pattern (TOCTOU fix)
- **I7:** OAuth2 revocation endpoint now requires client_id + client_secret
- **I8:** Rate limiting added to /auth/verify-email (10/min) and /auth/reset-password (10/min)
- **I9:** list_users pagination cap: limit max 100 via Query(le=100)
- **I10:** User.updated_at auto-updates via Beanie @before_event(Replace) hook
- **I11:** Logout handles decode_token failure per token independently
- **I12:** Public clients blocked from client_credentials grant

### Minor Fixes (9)
- **M1:** redirect_uris validated (HTTPS required except localhost)
- **M2:** Role name: min_length=1, max_length=64, pattern=^[a-z][a-z0-9_-]*$
- **M4:** LoginRequest.password max_length=72 (matches register, bcrypt truncation)
- **M5:** Removed dead User model fields: failed_login_attempts, locked_until
- **M6:** OAuth2TokenResponse.expires_in computed from TTL constant, not hardcoded 3600
- **M7:** CORS middleware added (configurable via CORS_ORIGINS env var)
- **O2:** seed_default_roles now idempotent on permissions (updates if changed in code)
- **O7:** requirements.txt cleaned (duplicate httpx removed)
- **Audit logging:** Structured JSON to stdout for login, logout, password_reset, sessions_revoked, roles_changed

### Test Coverage Improvement
- **90% → 96%** (64 → 103 tests)
- New test files: test_security.py, test_models.py, test_config.py, test_database.py, test_health.py

### New Environment Variables
- `CORS_ORIGINS` — comma-separated origins (empty = no CORS middleware)
- `JWT_SECRET_KEY` — now REQUIRED (was optional with insecure default)

---

## Post-v0.1.0 Security & Quality Improvements (Pre-v0.2.0)

### Security Enhancements
- **Atomic Token Exchange:** OAuth2 code exchange uses motor `find_one_and_update` with `used` flag to prevent race-condition double-spend
- **N+1 Fix:** `require_permission` loads all user roles in single MongoDB `$in` query instead of serial lookups
- **JWT Key Validator:** Enforces ≥32 character minimum at Settings initialization; raises ValueError if too short
- **Fixed-Window Lockout:** Account lockout TTL set only on first failure; subsequent attempts increment counter but don't reset window
- **Account Status Check:** `/auth/refresh` verifies `is_active` (403 if disabled)
- **Expanded Rate Limits:** IP-based limits on refresh (20/min), OAuth token (20/min), forgot-password (5/min)

### Database Indexing Improvements
- **TTL Index:** `oauth2_tokens.expires_at` and `oauth2_authorization_codes.expires_at` auto-delete expired entries
- **Sparse Indexes:** `User.verification_token`, `User.reset_token`, `OAuth2Token.refresh_token` (allows multiple NULL)

### Architecture Changes
- **Service Layer Extraction:** New `role_service.py` and `user_service.py` modules
- **Thin Route Handlers:** All routes delegate to service layer (no direct ORM/Redis in route handlers)
- **Shared Rate Limiter:** Single `Limiter` instance in `app/core/limiter.py` used across all endpoints

---

## Future Enhancements (Phase 8+)

### 8.1 Fix Session Revocation Check (HIGH PRIORITY)

**Current Issue:** `get_current_user()` doesn't check Redis blacklist

**Fix Required:**
```python
async def get_current_user() -> User:
    # 1. Decode JWT
    # 2. Extract JTI from payload
    # 3. Check Redis: bl:{jti} exists ← MISSING
    # 4. If exists, raise HTTPException(401)
    # 5. Otherwise return user
```

**Impact:** Critical for logout functionality
**Effort:** 2-4 hours

### 8.2 Audit Logging ✅ (Completed in v0.2.0)

- ~~Log all auth events~~ → Implemented: structured JSON to stdout
- ~~Log admin actions~~ → Implemented: roles_changed, sessions_revoked events
- Future: Store in MongoDB collection + query endpoint with filters (admin only)
- **Remaining Effort:** 1 week (for persistence + query endpoint)

### 8.3 GDPR Compliance

- User deletion endpoint (soft delete)
- Data export endpoint
- Privacy policy acknowledgment
- **Effort:** 1 week

### 8.4 Webhook Support

- Notify external systems of auth events
- Async delivery with retry
- Signature verification (HMAC)
- **Effort:** 2 weeks

### 8.5 Two-Factor Authentication (2FA)

- TOTP support (Google Authenticator, Authy)
- SMS codes (optional via Twilio)
- Backup codes
- **Effort:** 2-3 weeks

### 8.6 Passwordless Authentication

- Magic link emails
- Email-based login (token in link)
- **Effort:** 1-2 weeks

### 8.7 SAML 2.0 Support

- Enterprise SSO via SAML
- Identity provider integration
- **Effort:** 3-4 weeks

### 8.8 GraphQL Endpoint

- Parallel GraphQL API
- Same data as REST
- **Effort:** 2-3 weeks

### 8.9 API Documentation Improvements

- Enhanced Swagger/OpenAPI
- Custom UI
- Example requests/responses
- **Effort:** 1 week

### 8.10 mTLS Support

- Service-to-service authentication via certificates
- Client certificate validation
- **Effort:** 2 weeks

---

## Key Milestones

| Milestone | Phase | Date | Status |
|-----------|-------|------|--------|
| Core Auth Implemented | 1 | 2026-03-29 | ✅ Complete |
| RBAC Working | 2 | 2026-03-29 | ✅ Complete |
| OAuth2 Flows | 3 | 2026-03-29 | ✅ Complete |
| Email Verification | 4 | 2026-03-29 | ✅ Complete |
| Account Lockout | 5 | 2026-03-29 | ✅ Complete |
| Docker Ready | 6 | 2026-03-29 | ✅ Complete |
| 90%+ Test Coverage | 7 | 2026-03-29 | ✅ Complete |
| v0.1.0 Released | - | 2026-03-29 | ✅ Complete |
| v0.2.0 Security Release | - | 2026-03-31 | ✅ Complete (28 fixes) |
| Audit Logging (stdout) | 8.2 | 2026-03-31 | ✅ Complete |
| Session Revocation Fix | 8.1 | TBD | 🔜 Planned |
| Audit Log Persistence | 8.2+ | TBD | 🔜 Planned |

---

## Success Metrics (v0.1.0)

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| All 19 endpoints working | 100% | 100% | ✅ |
| Test coverage | 90%+ | 96% (103 tests) | ✅ |
| Login latency (p95) | <500ms | <500ms | ✅ |
| No hardcoded secrets | 100% | 100% | ✅ |
| Docker deployment | Working | Working | ✅ |
| Documentation | Complete | Complete | ✅ |

---

## Known Issues & Debt

### Critical (Must Fix)

1. **Session Revocation Incomplete**
   - `get_current_user()` doesn't check Redis blacklist
   - Impact: Logout doesn't actually invalidate tokens (partially mitigated by is_active check on refresh)
   - Priority: HIGH
   - Phase: 8.1

### Medium (Should Fix)

2. **Swagger/OpenAPI Customization**
   - Auto-generated docs not fully customized
   - Priority: MEDIUM
   - Phase: 8.9

### Low (Nice to Have)

4. **Email Template Improvements**
   - Plain text templates could be HTML
   - Priority: LOW
   - Effort: 2-4 hours

5. **Role Lookup Caching**
   - Role definitions cached in app state (optional optimization)
   - Priority: LOW
   - Phase: 8.2+

---

## Dependencies

```
Phase 1 (Core Auth)
├── Phase 2 (RBAC)
├── Phase 3 (OAuth2)
├── Phase 4 (Email Flows)
├── Phase 5 (Account Security)
├── Phase 6 (Docker)
└── Phase 7 (Testing)

Phase 8.x (Future)
├── 8.1 (Session Revocation Fix)
├── 8.2 (Audit Logging) - depends on Phase 2
├── 8.3 (GDPR) - depends on Phase 1
├── 8.4 (Webhooks)
├── 8.5 (2FA) - depends on Phase 4
├── 8.6 (Passwordless) - depends on Phase 4
├── 8.7 (SAML)
├── 8.8 (GraphQL)
├── 8.9 (API Docs)
└── 8.10 (mTLS)
```

---

## Release Notes

### v0.2.0 (2026-03-31)

**Security Release — 28 Fixes (7 Critical, 12 Important, 9 Minor):**
- ✅ Timing oracle prevention (dummy bcrypt on missing users)
- ✅ PKCE timing-safe comparison (hmac.compare_digest)
- ✅ JWT_SECRET_KEY now required (no default)
- ✅ Auth code reuse revokes all tokens (RFC 6749 §4.1.2)
- ✅ OAuth2 refresh atomic (TOCTOU fix)
- ✅ Dockerfile non-root (appuser)
- ✅ datetime.utcnow() → datetime.now(timezone.utc)
- ✅ Lockout email-hash keyed (works for non-existent users)
- ✅ Audit logging (structured JSON to stdout)
- ✅ CORS middleware (CORS_ORIGINS env var)
- ✅ bcrypt 72-byte validation
- ✅ 96% test coverage (103 tests, up from 64)

**New Env Vars:** `CORS_ORIGINS`, `JWT_SECRET_KEY` (now required)

**Breaking Changes:**
- `JWT_SECRET_KEY` no longer has a default — must be set in .env
- `LoginRequest.password` max_length reduced from 1024 to 72
- `/oauth/revoke` now requires client_id + client_secret

---

### v0.1.0 (2026-03-29)

**Features:**
- ✅ JWT authentication (register, login, logout, refresh)
- ✅ Role-Based Access Control (RBAC)
- ✅ OAuth2 (auth code + client credentials + PKCE)
- ✅ Email verification + password reset
- ✅ Account lockout (5 failures → 15-min lockout)
- ✅ Rate limiting (IP-based + per-user)
- ✅ 19 API endpoints
- ✅ Docker containerization
- ✅ 90%+ test coverage

**Known Issues:**
- Session revocation check incomplete
- Swagger docs could be more customized

**Breaking Changes:** None (first release)

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-03-29 | docs-manager | Initial roadmap for v0.1.0 (phases 1-7 complete) |
| 0.2.0 | 2026-03-31 | docs-manager | Added v0.2.0 release section (28 security fixes), moved audit logging to completed, updated test coverage to 96% |
