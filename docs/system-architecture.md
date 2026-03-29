# System Architecture

High-level design, component interactions, and data flows.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                       │
│        (Web Browser, Mobile App, Service)                    │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/REST
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   FastAPI Web Server                         │
│                 (Uvicorn, 0.0.0.0:8000)                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │       HTTP Routes (auth, roles, oauth2, users)       │   │
│  └────────────┬────────────────────────────────────────┘   │
│               │                                             │
│  ┌────────────▼──────────────────────────────────────────┐  │
│  │    Dependency Injection (get_current_user, roles)     │  │
│  └────────────┬──────────────────────────────────────────┘  │
│               │                                             │
│  ┌────────────▼──────────────────────────────────────────┐  │
│  │         Service Layer (Business Logic)                │  │
│  │  auth_service, oauth2_service, role_service,         │  │
│  │  user_service, lockout_service, email_service        │  │
│  └────────────┬──────────────────────────────────────────┘  │
│               │                                             │
│  ┌────────────▼──────────────────────────────────────────┐  │
│  │    Data Layer (Models, Security, Database)            │  │
│  └────────────┬──────────────────────────────────────────┘  │
└────────────────┼────────────────────────────────────────────┘
                 │
        ┌────────┴──────────┬───────────────────┐
        │                   │                   │
    ┌───▼────────┐   ┌──────▼─────┐  ┌────────▼──────┐
    │   MongoDB  │   │   Redis    │  │  SMTP Server  │
    │   (Data)   │   │  (Cache)   │  │   (Email)     │
    │            │   │            │  │               │
    │ Collections│   │ Keys:      │  │ Async SMTP    │
    │ - users    │   │ - bl:{jti} │  │               │
    │ - roles    │   │ - rl:email │  │               │
    │ - oauth2   │   │ - lockout  │  │               │
    │ - tokens   │   │            │  │               │
    └────────────┘   └────────────┘  └───────────────┘
```

---

## Authentication Flow

```
User Registration → Email Verification → Login → Token Refresh/Logout

1. Register
   POST /auth/register (email, password)
   → Hash password (bcrypt)
   → Create User in MongoDB
   → Send verification email
   → Return 201

2. Verify Email
   POST /auth/verify-email (email, token)
   → Validate token (1-hour expiry)
   → Mark user as verified
   → Return 200

3. Login
   POST /auth/login (email, password)
   → Fetch user from MongoDB
   → Verify password (bcrypt)
   → Check if locked (Redis)
   → Create JWT tokens (access: 30min, refresh: 7days)
   → Return tokens

4. Refresh
   POST /auth/refresh (refresh_token)
   → Decode refresh token
   → Check if blacklisted (Redis)
   → Create new access token
   → Return new token

5. Logout
   POST /auth/logout
   Authorization: Bearer {access_token}
   → Extract JTI from token
   → Add to Redis blacklist (bl:{jti})
   → Return 204
```

---

## OAuth2 Authorization Code Flow

```
Third-party Client
   │
   ├─ 1. User clicks "Login with AAA"
   │
   ├─ 2. Redirect to GET /oauth/authorize
   │      ?client_id=X&response_type=code&redirect_uri=Y&state=Z&code_challenge=C
   │
   ├─ 3. User logs in (requires JWT)
   │
   ├─ 4. AAA generates auth code (10-min expiry)
   │      Redirects to Y?code=X&state=Z
   │
   ├─ 5. Client app validates state, sends code back to backend
   │
   ├─ 6. Backend calls: POST /oauth/token
   │      grant_type=authorization_code
   │      code=X, client_id, client_secret, code_verifier
   │
   ├─ 7. AAA validates:
   │      - Code not expired
   │      - Client credentials match
   │      - PKCE: SHA256(verifier) == challenge
   │
   ├─ 8. Return access token + refresh token
   │
   └─ 9. Client app now has tokens for API calls
```

---

## RBAC Model

```
User "alice"
├── Role "admin"
│   └── Permissions: users:read, users:write, roles:manage
└── Role "manager"
    └── Permissions: users:read

Endpoint: GET /users
├── Requires: users:read
└── Result: alice can access (has via both roles)

Endpoint: DELETE /roles/{id}
├── Requires: roles:delete
└── Result: alice can delete (has via admin role)
```

---

## Rate Limiting & Lockout

### IP-based & Shared Rate Limiting

All rate-limited endpoints use shared `Limiter` instance from `app/core/limiter.py`:

| Endpoint | Limit | Window |
|----------|-------|--------|
| POST /auth/register | 10 req/min | Per IP |
| POST /auth/login | 10 req/min | Per IP |
| POST /auth/refresh | 20 req/min | Per IP |
| POST /auth/forgot-password | 5 req/min | Per IP |
| POST /auth/reset-password | 5 req/min | Per IP |
| POST /oauth/token | 20 req/min | Per IP |
| GET /oauth/authorize | 10 req/min | Per IP |

### Account Lockout (Fixed-Window)

```
Failed login attempt:
   │
   ├─ Increment Redis: lockout:{user_id}
   │
After 1st failure:
   ├─ Count = 1
   ├─ Set TTL to 15 minutes (fixed window)
   └─ Allow retry
   │
After 5 failures (within 15-min window):
   │
   ├─ Count reaches 5
   └─ Return HTTP 403 Locked

After TTL expires (15 minutes from first failure):
   │
   ├─ Redis key auto-deletes
   ├─ Account unlocked
   └─ User can retry login

Note: TTL set only on first failure, not on subsequent attempts
      (fixed-window lockout, not sliding)
```

### Email Rate Limiting (Per-User, 3/hour)

```
POST /auth/forgot-password or /auth/reset-password:
   │
   ├─ Redis: INCR rl:email:{email}
   ├─ Count 1-3: Allow, send email
   ├─ Count 4+: Return HTTP 429 Too Many Requests
   └─ TTL: 1 hour (reset hourly)
```

---

## Database Schema Summary

### Users Collection
```
{
  "_id": ObjectId,
  "email": "user@example.com",    # unique index
  "password_hash": "bcrypt...",
  "is_verified": true,
  "roles": ["user", "admin"],
  "failed_login_attempts": 0,
  "created_at": ISODate
}
```

### Roles Collection
```
{
  "_id": ObjectId,
  "name": "admin",                # unique index
  "permissions": ["users:*", "roles:*"],
  "description": "Full admin access",
  "created_at": ISODate
}
```

### OAuth2 Clients Collection
```
{
  "_id": ObjectId,
  "client_id": "generated-id",    # unique index
  "client_secret": "bcrypt...",
  "client_name": "My App",
  "redirect_uris": ["https://app.example.com/callback"],
  "owner_id": ObjectId,
  "created_at": ISODate
}
```

### OAuth2 Tokens Collection
```
{
  "_id": ObjectId,
  "code": "auth-code",            # unique index
  "access_token": "jwt...",       # unique index
  "refresh_token": "jwt...",      # sparse unique index
  "user_id": ObjectId,
  "client_id": "oauth-client",
  "expires_at": ISODate,          # TTL index (auto-delete when expired)
  "used": false,                  # prevents double-spend on code exchange
  "revoked": false,
  "created_at": ISODate
}
```

### OAuth2 Authorization Codes Collection
```
{
  "_id": ObjectId,
  "code": "auth-code",            # unique index
  "client_id": "oauth-client",
  "user_id": ObjectId,
  "code_challenge": "...",        # PKCE challenge (S256)
  "expires_at": ISODate,          # TTL index (auto-delete when expired)
  "used": false,                  # prevents double-spend
  "created_at": ISODate
}
```

### Redis Keys
```
bl:{jti}               → expiry_timestamp  (JWT blacklist)
rl:email:{email}       → counter            (email rate limit)
lockout:{user_id}      → counter            (failed login attempts)
revoked_at:{user_id}   → timestamp          (session revocation)
```

---

## Security Layers

```
Layer 1: Input Validation (Pydantic)
├─ Email format validation
├─ Password requirements (8+ chars)
├─ Password max_length=1024 (bcrypt DoS prevention)
└─ Field type/length enforcement

Layer 2: Authentication
├─ Password hashing (bcrypt, 12 rounds)
├─ JWT signing (HS256)
├─ JWT key validator (≥32 char minimum at startup)
├─ Account lockout (fixed-window, 15 min after 5 failures)
└─ Token revocation (Redis blacklist with JTI)

Layer 3: Authorization
├─ Role-based checking (N+1 fix: single MongoDB $in query)
├─ Permission checking
└─ Account status check on token refresh (is_active)

Layer 4: Rate Limiting
├─ IP-based (slowapi) per endpoint
├─ Email-based (Redis) 3/hour
├─ Lockout counter (Redis fixed-window)
└─ All sensitive endpoints rate-limited (shared limiter instance)

Layer 5: OAuth2 Security
├─ Atomic code exchange (motor find_one_and_update)
├─ Prevents double-spend (used flag check)
├─ PKCE validation (S256: SHA256(verifier) == challenge)
└─ Client secret hashing (bcrypt)

Layer 6: Data Security
├─ HTTPS in transit
├─ Password hashing at rest (bcrypt)
├─ Client secret hashing (bcrypt)
├─ MongoDB TTL indexes (auto-delete expired tokens/codes)
└─ JWT token caching (Redis)
```

---

## Deployment Architecture

```
┌──────────────────────────────────────┐
│   Load Balancer / Reverse Proxy      │
│        (nginx, HAProxy)              │
│   (HTTPS termination here)           │
└────────────────┬─────────────────────┘
         ┌───────┼────────┐
         │       │        │
    ┌────▼──┐ ┌──▼──┐ ┌──▼──┐
    │App 1  │ │App 2 │ │App 3 │  (Stateless)
    └────┬──┘ └──┬──┘ └──┬──┘
         └───────┼────────┘
         ┌───────┼────────┐
    ┌────▼────┐ ┌─▼────┐ ┌──▼──┐
    │ MongoDB │ │Redis │ │SMTP │
    │Cluster  │ │Cluster│      │
    └─────────┘ └──────┘ └──────┘
```

---

## API Endpoint Summary

### Authentication (7 endpoints)
- POST /auth/register
- POST /auth/login
- POST /auth/logout
- POST /auth/refresh
- POST /auth/verify-email
- POST /auth/forgot-password
- POST /auth/reset-password

### Roles (4 endpoints - admin only)
- POST /roles
- GET /roles
- PUT /roles/{id}
- DELETE /roles/{id}

### OAuth2 (5 endpoints)
- POST /oauth/clients
- GET /oauth/clients
- GET /oauth/authorize
- POST /oauth/token
- POST /oauth/revoke

### Users (3 endpoints)
- GET /users
- POST /users/{id}/roles
- DELETE /users/{id}/sessions

### System (1 endpoint)
- GET /health

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-03-29 | docs-manager | Initial system architecture for v0.1.0 |
