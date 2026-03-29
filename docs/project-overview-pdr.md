# Project Overview & Product Development Requirements (PDR)

## Executive Summary

**Authentication & Authorization System (AAA)** is a production-grade FastAPI service providing secure user authentication, role-based access control, OAuth2 integration, and account security features. Targets SaaS platforms, internal systems, and microservices requiring centralized auth without vendor lock-in.

**Status:** v0.1.0 - Core implementation complete, 90%+ test coverage, ready for integration.

---

## Product Vision

### Goals

1. **Secure by Default:** JWT + OAuth2 + bcrypt + rate limiting + lockout protection
2. **Developer-Friendly:** Clear API, comprehensive docs, Docker-ready, async-native
3. **Production-Ready:** Comprehensive test coverage, Docker containerization, health checks
4. **Extensible:** Service-oriented architecture supports future features (audit logging, webhooks, SAML)

### Target Users

- **Backend Developers:** Integrate via REST API, SDKs to be added
- **DevOps:** Docker deployment, environment-based config, health monitoring
- **Security Teams:** RBAC audit trails, session revocation, lockout policies, rate limits

### Core Problems Solved

| Problem | Solution |
|---------|----------|
| Insecure passwords | bcrypt hashing + password reset flows |
| Unauthorized access | JWT + RBAC with granular permissions |
| Account takeover | Email verification + password reset + lockout |
| Token misuse | JTI-based revocation, Redis blacklist, refresh token rotation |
| Bot/brute-force attacks | Rate limiting (IP-based + per-user), account lockout |
| Session hijacking | Per-user session revocation via Redis |
| Third-party integration | OAuth2 authorization code + PKCE flows |

---

## Functional Requirements

### 1. User Authentication

**FR1.1 - User Registration**
- Accept email + password
- Hash password with bcrypt
- Create user document in MongoDB
- Send verification email (1-hour expiry)
- Return 201 + user ID on success
- Prevent duplicate emails (enumeration-safe)

**FR1.2 - Email Verification**
- Accept email + verification token
- Validate token (not expired, not tampered)
- Mark user as verified
- Return 200 on success, 400 if invalid/expired

**FR1.3 - User Login**
- Accept email + password
- Verify email is registered + verified
- Verify password against bcrypt hash
- Create JWT access token + refresh token
- Return both tokens (30min access, 7-day refresh)
- Increment failed attempt counter on failure
- Trigger 15-min lockout after 5 failures

**FR1.4 - Token Refresh**
- Accept refresh token
- Validate JTI not in Redis blacklist
- Create new access token
- Return new token (do NOT reset TTL of refresh token)

**FR1.5 - User Logout**
- Accept access token
- Extract JTI, add to Redis blacklist with TTL = token expiry
- Return 204 on success

**FR1.6 - Password Reset**
- Accept email
- Generate 30-min expiring reset token
- Send email with token
- Accept email + token + new password
- Validate token, hash new password
- Return 200 on success

### 2. Role-Based Access Control (RBAC)

**FR2.1 - Role Management (Admin-only)**
- Create role: accept name + permissions list
- List roles: return all roles
- Update role: modify name/permissions (protect default roles)
- Delete role: prevent deletion of default "admin" + "user" roles

**FR2.2 - Permission Model**
- Permissions as strings (e.g., `users:read`, `roles:write`)
- Roles contain list of permissions
- Users have list of assigned roles

**FR2.3 - Access Control**
- `get_current_user()` dependency: extract user from JWT
- `require_role()` dependency: check user has role
- `require_permission()` dependency: check user has permission (via roles)
- N+1 fix: Single MongoDB `$in` query loads all user roles in one call
- Return 403 Forbidden if missing permissions

**FR2.4 - Default Roles**
- "admin": full permissions (users:*, roles:*, permissions:*)
- "user": basic permissions (users:read)
- Seed on app startup, prevent deletion

### 3. OAuth2 Flow

**FR3.1 - OAuth2 Client Registration**
- Accept client_name, redirect_uris
- Generate client_id + client_secret
- Return credentials (secret shown once)
- Protect endpoint (admin only)

**FR3.2 - Authorization Code Flow (RFC 6749)**
- GET `/oauth/authorize?client_id=X&response_type=code&redirect_uri=Y&state=Z&code_challenge=C&code_challenge_method=S256`
- Current user must be logged in (via JWT)
- Generate 10-min auth code
- Redirect to `redirect_uri?code=X&state=Z`
- Return 400 if client_id invalid, redirect_uri mismatch

**FR3.3 - Token Exchange (RFC 6749)**
- POST `/oauth/token` with `grant_type=authorization_code`
- Exchange auth code + client_id + client_secret + code_verifier for access token
- Validate PKCE (S256: base64url(sha256(verifier)) == challenge)
- Return access token (30-min JWT) + optional refresh token

**FR3.4 - Client Credentials Flow**
- POST `/oauth/token` with `grant_type=client_credentials`
- Authenticate via client_id + client_secret (HTTP Basic or body)
- Return access token (no user context)
- Useful for service-to-service auth

**FR3.5 - Token Revocation (RFC 7009)**
- POST `/oauth/revoke` with token
- Verify token, add to Redis blacklist
- Return 200 (even if token invalid, for security)

### 4. Account Security

**FR4.1 - Email Rate Limiting**
- Track email attempts per user (Redis)
- Allow 3 attempts per hour
- Return 429 Too Many Requests if exceeded
- Reset counter hourly

**FR4.2 - Account Lockout**
- Track failed login attempts per user (Redis)
- Lock account after 5 failures
- Lockout duration: 15 minutes (fixed-window from first failure)
- TTL set only on first failure (not reset on subsequent failures)
- Reset counter on successful login or after TTL expiry
- Return 403 Locked if account locked

**FR4.3 - Session Revocation**
- Admin can revoke all sessions for a user
- Add all JTIs to Redis blacklist
- Invalidate all existing tokens immediately

### 5. Email Service

**FR5.1 - Async Email**
- Send via aiosmtplib (async SMTP)
- Template emails (verification, reset)
- Graceful failure (log error, don't crash)
- Configurable SMTP via .env

---

## Non-Functional Requirements

### Performance (NFR1)

| Metric | Target | Implementation |
|--------|--------|-----------------|
| Login latency | <500ms (p95) | Async, Redis cache, index on email |
| Register latency | <1s (p95) | Async email (non-blocking) |
| Token validation | <10ms (p95) | JWT decode in-memory, Redis cache |
| Throughput | 100+ RPS per node | Async I/O, connection pooling |

### Scalability (NFR2)

- **Horizontal:** Stateless app, shared MongoDB + Redis
- **Database:** MongoDB with unique indexes (email, client_id)
- **Cache:** Redis for JWT blacklist, rate limits, lockout counters
- **Load:** Designed for 1000+ concurrent users per node

### Security (NFR3)

| Concern | Control |
|---------|---------|
| Password Storage | bcrypt with salt (12 rounds) |
| Password DoS | Pydantic max_length=1024 on password input |
| Token Tampering | HMAC-SHA256 signature (HS256) |
| JWT Key Strength | Validator enforces ≥32 char minimum at startup |
| Token Expiration | iat + exp claims, Redis blacklist |
| Token Double-Spend | Atomic motor find_one_and_update (used flag) |
| Brute Force | Rate limiting (IP-based) + account lockout (fixed-window) |
| Role N+1 Queries | Single MongoDB $in query loads all roles at once |
| Email Enumeration | Same response for valid/invalid emails |
| CSRF | SameSite cookies + token-based API |
| SQL Injection | ODM (Beanie) prevents injection |
| XSS | API returns JSON (no HTML rendering) |
| CORS | Configurable origins (default: none) |
| HTTPS | Ready (reverse proxy responsibility) |
| Session Revocation | Account disablement checked on token refresh (is_active) |
| Expired Token Cleanup | MongoDB TTL indexes auto-delete tokens & codes |

### Reliability (NFR4)

- **Availability:** 99.9% uptime target (with proper Redis + MongoDB HA)
- **Data Durability:** MongoDB replication, Redis persistence
- **Error Handling:** Graceful degradation, detailed logs
- **Health Checks:** `/health` endpoint for monitoring

### Maintainability (NFR5)

- **Code Coverage:** 90%+ unit + integration test coverage
- **Documentation:** README + 7 doc files + docstrings
- **Type Safety:** Python type hints throughout
- **Modularity:** Service layer + dependency injection

### Compliance (NFR6)

- **GDPR:** User deletion not yet implemented (TODO)
- **OAuth2:** RFC 6749, RFC 7636, RFC 7009 compliance
- **JWT:** RFC 7519 standard claims
- **OWASP:** OWASP Top 10 controls in place

---

## Success Metrics

### Functional Completeness

- [ ] All 19 API endpoints implemented + tested
- [ ] All auth flows (register → login → logout → refresh) working
- [ ] All RBAC endpoints (create/read/update/delete roles) working
- [ ] OAuth2 all grant types (auth code, client credentials, revocation) working
- [ ] Email verification + password reset flows working
- [ ] Account lockout triggering correctly
- [ ] Rate limiting enforced
- [ ] Session revocation working

### Test Coverage

- [ ] 90%+ overall coverage
- [ ] All critical paths tested (happy path + error cases)
- [ ] Integration tests with real MongoDB + Redis (testcontainers)
- [ ] All edge cases covered (lockout, rate limit, expired tokens)

### Performance

- [ ] Login latency <500ms (p95)
- [ ] No memory leaks (test for 1000+ requests)
- [ ] Connection pooling working (verify pool size)

### Documentation

- [ ] README covers setup + API overview
- [ ] API docs auto-generated (FastAPI Swagger)
- [ ] All functions have docstrings
- [ ] Deployment guide covers Docker + manual
- [ ] Code standards doc defines patterns

### Security

- [ ] No hardcoded secrets in code
- [ ] All passwords hashed with bcrypt
- [ ] JWT tokens signed + validated
- [ ] Rate limiting enforced
- [ ] Account lockout working
- [ ] Email enumeration prevented
- [ ] HTTPS ready (config in docs)

---

## Acceptance Criteria

### Implementation Definition of Done

1. **Code**
   - All 19 endpoints implemented
   - No syntax errors, code compiles
   - Type hints on all functions
   - Docstrings on all public functions

2. **Tests**
   - 90%+ coverage (pytest --cov)
   - All tests pass locally + in CI
   - Integration tests with testcontainers
   - No flaky tests

3. **Documentation**
   - README.md with quick start
   - 7 docs files completed
   - Swagger/OpenAPI auto-docs accessible
   - Deployment guide written

4. **Security**
   - No secrets in git (.gitignore checked)
   - JWT secret rotation guidance
   - Password hashing with bcrypt verified
   - Rate limiting + lockout tested

5. **DevOps**
   - Dockerfile builds successfully
   - docker-compose brings up all services
   - Health check endpoint working
   - Environment variables documented

---

## Known Limitations & Future Work

### Current Limitations

1. **Session Revocation:** `get_current_user()` doesn't check Redis blacklist (incomplete implementation)
2. **GDPR:** No user deletion endpoint
3. **Audit Logging:** No request/action audit trail
4. **Webhooks:** No webhook support for events (user created, password reset, etc.)
5. **SAML:** OAuth2-only, no SAML 2.0 support
6. **2FA:** No two-factor authentication
7. **Passwordless:** No magic links or passwordless flows
8. **API Docs:** Swagger UI not fully customized

### Phase 8 (Future)

- [ ] Fix session revocation check in `get_current_user()`
- [ ] Add audit logging (API request log + auth event log)
- [ ] Implement user deletion (GDPR compliance)
- [ ] Add webhook support (user created, password reset, login failed)
- [ ] Add 2FA (TOTP via pyotp)
- [ ] Add magic link authentication
- [ ] Add SAML 2.0 support
- [ ] Improve Swagger/OpenAPI documentation
- [ ] Add GraphQL endpoint (optional)
- [ ] Add mTLS support for service-to-service auth

---

## Stakeholder Sign-Off

| Role | Name | Status |
|------|------|--------|
| Product Owner | [TBD] | Pending |
| Tech Lead | [TBD] | Pending |
| Security Lead | [TBD] | Pending |
| DevOps Lead | [TBD] | Pending |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-03-29 | docs-manager | Initial PDR for v0.1.0 (core auth, RBAC, OAuth2, email, lockout, Docker, tests) |
