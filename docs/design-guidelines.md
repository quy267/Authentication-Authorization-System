# Design Guidelines

API design principles, architectural decisions, and best practices.

---

## API Design Principles

### 1. RESTful Design

Endpoints follow REST conventions:

| HTTP Method | Purpose | Status Codes |
|-------------|---------|--------------|
| GET | Retrieve resource(s) | 200, 404 |
| POST | Create resource | 201, 400, 409 |
| PUT | Update resource | 200, 400, 404 |
| DELETE | Delete resource | 204, 404 |

**Example Endpoints:**
```
GET    /users           # List users
POST   /users           # Create user
GET    /users/{id}      # Get user
PUT    /users/{id}      # Update user
DELETE /users/{id}      # Delete user
```

### 2. Consistent Response Format

**Success Response (2xx):**
```json
{
  "data": { /* resource */ },
  "meta": { "timestamp": "2026-03-29T10:00:00Z" }
}
```

**Error Response (4xx, 5xx):**
```json
{
  "detail": "Error message",
  "status_code": 400
}
```

### 3. Status Codes

| Code | Usage | Example |
|------|-------|---------|
| 200 | Success (GET, PUT) | User retrieved |
| 201 | Resource created (POST) | User registered |
| 204 | No content (DELETE) | User logged out |
| 400 | Bad request | Invalid email |
| 401 | Unauthorized | Invalid credentials |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not found | User not found |
| 409 | Conflict | Email already registered |
| 429 | Too many requests | Rate limit exceeded |
| 500 | Server error | Unexpected exception |

### 4. Error Handling

Consistent error responses:

**Authentication Error:**
```json
HTTP/1.1 401 Unauthorized
{"detail": "Invalid email or password"}
```

**Authorization Error:**
```json
HTTP/1.1 403 Forbidden
{"detail": "Insufficient permissions"}
```

**Validation Error:**
```json
HTTP/1.1 422 Unprocessable Entity
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

---

## Authentication Design

### JWT Token Structure

**Access Token Payload:**
```json
{
  "sub": "507f1f77bcf86cd799439011",  // User ID
  "roles": ["user", "admin"],         // User roles
  "type": "access",                   // Token type
  "jti": "550e8400-e29b-41d4-...",   // Unique token ID
  "iat": 1234567890,                  // Issued at
  "exp": 1234569690                   // Expiration
}
```

**Refresh Token Payload:**
```json
{
  "sub": "507f1f77bcf86cd799439011",
  "type": "refresh",
  "jti": "550e8400-e29b-41d4-...",
  "iat": 1234567890,
  "exp": 1234914290                   // 7 days
}
```

### Token Usage

**Request with Bearer Token:**
```bash
GET /users
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response if Invalid/Expired:**
```json
HTTP/1.1 401 Unauthorized
{"detail": "Invalid authentication credentials"}
```

---

## Authorization Design

### Role-Based Access Control (RBAC)

**Model:**
- Users have **roles**
- Roles have **permissions**
- Endpoints require specific permissions

**Example:**
```
User "alice"
├── Role "admin"
│   └── Permissions: users:read, users:write, roles:*
└── Role "manager"
    └── Permissions: users:read

Endpoint GET /users
├── Requires: users:read permission
└── Result: alice can access (has via both roles)
```

### Default Roles

| Role | Permissions | Protected | Usage |
|------|-------------|-----------|-------|
| admin | Full access (users:*, roles:*) | Yes | System administrators |
| user | Read-only (users:read) | Yes | Regular users |

### Permission Format

Permissions follow `resource:action` convention:

| Permission | Resource | Action | Usage |
|-----------|----------|--------|-------|
| `users:read` | users | read | Get user info |
| `users:write` | users | write | Update user |
| `roles:read` | roles | read | List roles |
| `roles:write` | roles | write | Update role |
| `roles:manage` | roles | manage | Create/delete roles |

---

## Database Design

### Document Model Choices

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Database | MongoDB | Flexible schema, horizontal scaling |
| ODM | Beanie | Async support, Pydantic integration |
| Structure | Document-based | Denormalized for read performance |

### Collection Design

**users Collection:**
- Primary key: `_id` (ObjectId)
- Unique index: `email`
- Array field: `roles` (denormalized for JWT)
- Rationale: Fast email lookup, role info embedded

**roles Collection:**
- Primary key: `_id` (ObjectId)
- Unique index: `name`
- Array field: `permissions`
- Rationale: Central role definitions

**oauth2_clients Collection:**
- Primary key: `_id` (ObjectId)
- Unique index: `client_id`
- Rationale: OAuth2 client registration

**oauth2_tokens Collection:**
- Multi-use: Auth codes + tokens
- Unique indexes: `code`, `access_token`
- Rationale: Single document per auth flow

### Indexing Strategy

**Unique Indexes:**
```javascript
db.users.createIndex({ email: 1 }, { unique: true })
db.roles.createIndex({ name: 1 }, { unique: true })
db.oauth2_clients.createIndex({ client_id: 1 }, { unique: true })
db.oauth2_tokens.createIndex({ code: 1 }, { unique: true })
db.oauth2_tokens.createIndex({ access_token: 1 }, { unique: true })
```

**Sparse Indexes (allow multiple NULL):**
```javascript
db.users.createIndex({ verification_token: 1 }, { sparse: true })
db.users.createIndex({ reset_token: 1 }, { sparse: true })
db.oauth2_tokens.createIndex({ refresh_token: 1 }, { sparse: true, unique: true })
```

**TTL Indexes (auto-delete on expiry):**
```javascript
db.oauth2_tokens.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0 })
db.oauth2_authorization_codes.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0 })
```

**Rationale:**
- Sparse indexes prevent index bloat on optional token fields (multiple NULL values allowed)
- TTL indexes auto-cleanup expired OAuth2 tokens and authorization codes
- No manual cleanup jobs or background tasks needed

---

## Security Design

### Defense in Depth

```
Layer 1: Input Validation (Pydantic)
├─ Email format
├─ Password requirements
└─ Field type/length

Layer 2: Rate Limiting
├─ IP-based (slowapi)
├─ Email-based (Redis)
└─ Account lockout (Redis)

Layer 3: Authentication
├─ Password hashing (bcrypt)
├─ JWT signing (HS256)
└─ Token revocation (Redis)

Layer 4: Authorization
├─ Role checking
└─ Permission checking

Layer 5: Data Encryption
├─ HTTPS in transit
├─ Password hashing at rest
└─ Client secret hashing
```

### Password Security

**Requirements:**
- Minimum 8 characters
- Maximum 1024 characters (DoS prevention via Pydantic `max_length`)
- Hashed with bcrypt (12 rounds, salt included)
- Timing-safe comparison
- Never logged or displayed

**DoS Prevention:**
- Pydantic `LoginRequest.password = Field(max_length=1024)` validates input before bcrypt
- Prevents oversized input attacks that could consume CPU during hashing
- Validation occurs in dependency injection layer before password comparison

**Storage:**
```json
{
  "email": "user@example.com",
  "password_hash": "$2b$12$..."  // bcrypt, never plaintext
}
```

### OAuth2 Security

**PKCE (RFC 7636):**
- Client creates random `code_verifier`
- Sends `code_challenge = base64url(SHA256(verifier))`
- On token exchange, verifies: `SHA256(verifier) == challenge`

**Client Secrets:**
- Generated as random strings
- Hashed with bcrypt before storage
- Shown only once on creation
- Cannot be retrieved later

### Token Expiry

| Token Type | Expiry | Purpose |
|-----------|--------|---------|
| Auth code | 10 minutes | One-time exchange |
| Access token | 30 minutes | API access |
| Refresh token | 7 days | Get new access token |
| Verification token | 1 hour | Email verification |
| Reset token | 30 minutes | Password reset |

---

## Scalability Design

### Horizontal Scaling

**Stateless Application:**
- No server-side session storage
- JWT tokens contain user info
- Redis used only for ephemeral state
- Multiple app instances can run in parallel

**Database Scaling:**
```
MongoDB Replica Set:
├─ Primary (writes + reads)
├─ Secondary 1 (reads)
└─ Secondary 2 (reads + backup)

Redis Cluster:
├─ Node 1
├─ Node 2
└─ Node 3
```

**Load Balancing:**
```
Load Balancer (nginx)
├─ App 1
├─ App 2
└─ App 3 (Stateless)
    │
    └─ MongoDB + Redis
```

### Performance Optimization

**Caching Strategy:**
- JWT validation: In-memory (<10ms)
- Role lookup: N+1 fix — single MongoDB `$in` query loads all roles
- Email rate limit: Redis with TTL
- User session revocation TTL: Redis with configurable window

**Query Optimization:**
- Index on `email` (fast user lookup)
- Single `$in` query for require_permission (vs. N serial lookups)
- Denormalize roles in JWT payload (no extra query on each request)
- Connection pooling (10-50 MongoDB, 10-20 Redis)

**Rate Limiting:**
- Shared `Limiter` instance in `app/core/limiter.py`
- All endpoints use same rate limiter to avoid duplicate initialization
- IP-based limits: register/login 10/min, refresh/oauth-token 20/min, forgot-password 5/min

---

## Testing Design

### Test Pyramid

```
        ▲
       /│\
      / │ \  E2E Tests (5%)
     /  │  \
    /───┼───\  Integration Tests (25%)
   /    │    \
  /─────┼─────\  Unit Tests (70%)
 /_____┼_____\
```

**Unit Tests (70%):**
- Individual functions/methods
- No I/O (mock database)
- Fast execution (<1s each)
- Example: `test_hash_password`, `test_verify_password`

**Integration Tests (25%):**
- Service layer + database
- Real MongoDB + Redis (testcontainers)
- Example: `test_register_user`, `test_login_flow`

**E2E Tests (5%):**
- Full request → response cycle
- HTTP client + real services
- Example: `test_oauth2_auth_code_flow`

### Test Coverage

**Target:** 90%+ overall coverage

```bash
pytest --cov=app --cov-report=html
```

---

## Documentation Design

### Structure

```
docs/
├── README.md                      # Project overview
├── project-overview-pdr.md        # Requirements + goals
├── codebase-summary.md            # Code organization
├── code-standards.md              # Conventions + patterns
├── system-architecture.md         # Flows + diagrams
├── project-roadmap.md             # Phases + progress
├── deployment-guide.md            # Setup instructions
└── design-guidelines.md           # This file
```

### Types of Documentation

| Type | Purpose | Audience |
|------|---------|----------|
| README | Quick start | New developers |
| API Docs | Endpoint reference | Frontend developers |
| Architecture | System design | Tech leads |
| Code Standards | Implementation | Developers |
| Roadmap | Project status | Product team |
| Deployment | Setup guide | DevOps |

---

## Future Enhancements

**Phase 8+** considerations:

- **Audit Logging:** Log all auth events for compliance
- **Webhook Support:** Notify external systems of events
- **2FA / MFA:** TOTP, SMS, backup codes
- **Passwordless Auth:** Magic links, WebAuthn
- **SAML 2.0:** Enterprise SSO
- **GraphQL:** Parallel API
- **mTLS:** Service-to-service authentication

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-03-29 | docs-manager | Initial design guidelines for v0.1.0 |
