# Deployment Guide

Instructions for deploying in development, staging, and production.

---

## Development Environment

### Option 1: Docker Compose (Recommended)

```bash
# Copy environment template
cp .env.example .env

# Start all services
docker-compose up -d

# Verify health
curl http://localhost:8000/health

# View logs
docker-compose logs -f app

# Stop services
docker-compose down
```

**Services Running:**
- App: http://localhost:8000
- MongoDB: localhost:27017
- Redis: localhost:6379
- Swagger: http://localhost:8000/docs

### Option 2: Manual Setup

```bash
# Create venv
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start MongoDB & Redis separately
docker run -d -p 27017:27017 --name mongodb mongo:7
docker run -d -p 6379:6379 --name redis redis:7

# Copy environment
cp .env.example .env
# Edit .env with local connection strings

# Run app
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# In another terminal, run tests
pytest tests/ --cov=app --cov-report=html
```

---

## Staging Environment

### Configuration

Create `.env.staging`:

```bash
APP_NAME=Auth System (Staging)
DEBUG=False

# External instances (not localhost)
MONGODB_URL=mongodb://staging-mongo.internal:27017
MONGODB_DB_NAME=auth_db_staging
REDIS_URL=redis://staging-redis.internal:6379/0

# JWT (CHANGE THIS! Must be ≥32 chars)
JWT_SECRET_KEY=$(openssl rand -hex 32)
# Generate: openssl rand -hex 32 (produces 64-char hex string)
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# SMTP
SMTP_HOST=smtp.staging.internal
SMTP_PORT=587
SMTP_USER=noreply@staging.example.com
SMTP_PASSWORD=<secure-password>
EMAIL_FROM=noreply@staging.example.com

# Security
LOCKOUT_THRESHOLD=5
LOCKOUT_DURATION_MINUTES=15
```

### Docker Deployment

```bash
# Build image
docker build -t auth-system:0.1.0 .

# Run container
docker run -d \
  --name auth-system-staging \
  --env-file .env.staging \
  -p 8000:8000 \
  auth-system:0.1.0

# Verify health
curl http://localhost:8000/health
```

---

## Production Environment

### Security Checklist

Before going live:

- [ ] JWT_SECRET_KEY: **REQUIRED** — app will NOT start without it. Generate: `openssl rand -hex 32`
- [ ] SMTP credentials: In secrets manager (NOT in git)
- [ ] MongoDB password: Strong, non-default
- [ ] Redis password: Strong, non-default
- [ ] CORS_ORIGINS: Set to allowed domains only (empty = no CORS middleware)
- [ ] HTTPS: Enforced on all endpoints
- [ ] Rate limiting: Configured appropriately (verify-email 10/min, reset-password 10/min added in v0.2.0)
- [ ] Account lockout: Threshold appropriate
- [ ] Email verification: Required
- [ ] Database backups: Scheduled daily
- [ ] Docker: Verify container runs as non-root (`appuser`) — default since v0.2.0
- [ ] Audit logs: Monitor structured JSON stdout for security events (login, logout, password_reset, sessions_revoked, roles_changed)

### Configuration for Production

Create `.env.production`:

```bash
APP_NAME=Auth System
DEBUG=False

# External managed services
MONGODB_URL=mongodb+srv://user:password@prod-cluster.mongodb.net/auth_db
MONGODB_DB_NAME=auth_db
REDIS_URL=redis://:password@prod-redis.internal:6379/0

# JWT (REQUIRED — no default! App won't start without it. Enforced ≥32 chars)
# Generate: openssl rand -hex 32
JWT_SECRET_KEY=<64-char-hex-string-from-openssl-rand-hex-32>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# SMTP (use production relay)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=<api-key-from-vault>
EMAIL_FROM=noreply@yourdomain.com

# Security
LOCKOUT_THRESHOLD=5
LOCKOUT_DURATION_MINUTES=15
LOG_LEVEL=INFO

# CORS (set to allowed origins — empty means no CORS middleware)
CORS_ORIGINS=https://app.yourdomain.com,https://admin.yourdomain.com
```

**Store secrets in:**
- HashiCorp Vault
- AWS Secrets Manager
- Azure Key Vault
- Kubernetes Secrets
- Never commit .env.production to git

### Docker Production

> **Note:** Since v0.2.0, the Dockerfile runs as non-root user (`appuser`). No additional configuration needed.

```bash
# Build image
docker build -t auth-system:0.2.0 .

# Push to registry
docker tag auth-system:0.1.0 registry.prod.internal/auth-system:0.1.0
docker push registry.prod.internal/auth-system:0.1.0

# Run container
docker run -d \
  --name auth-system \
  --restart always \
  --env-file /etc/auth-system/.env.production \
  -p 127.0.0.1:8000:8000 \
  auth-system:0.1.0

# Verify health
curl http://localhost:8000/health
```

### Kubernetes Production

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-system
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: auth-system
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: auth-system
    spec:
      containers:
      - name: app
        image: registry.prod.internal/auth-system:0.1.0
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: auth-system-config
        - secretRef:
            name: auth-system-secrets
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 20
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: auth-system
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: auth-system
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Reverse Proxy (nginx)

```nginx
upstream auth_system {
    server localhost:8000;
}

server {
    listen 443 ssl http2;
    server_name auth.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/auth.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/auth.yourdomain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/s;
    limit_req zone=api burst=200 nodelay;

    location / {
        proxy_pass http://auth_system;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name auth.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

---

## Health Checks

```bash
GET /health
```

**Response (200 OK):**
```json
{"status": "ok"}
```

**Usage for monitoring:**
```bash
curl -f http://localhost:8000/health || exit 1
```

---

## Database Maintenance

### MongoDB Backups

```bash
# Manual backup
mongodump --uri "mongodb://user:pass@host:27017/auth_db" \
          --out /backups/auth_db_$(date +%Y%m%d)

# Restore backup
mongorestore --uri "mongodb://user:pass@host:27017" \
             /backups/auth_db_20260329
```

### Redis Persistence

Ensure Redis is configured for persistence:

```conf
# redis.conf
save 900 1                # Save if 1+ keys changed in 900s
save 300 10               # Save if 10+ keys changed in 300s
save 60 10000             # Save if 10000+ keys changed in 60s
appendonly yes            # AOF persistence
appendfsync everysec
```

### Index Verification & TTL Cleanup

```bash
# Connect to MongoDB
mongosh "mongodb://user:pass@host:27017/auth_db"

# List indexes
db.users.getIndexes()
db.roles.getIndexes()
db.oauth2_clients.getIndexes()
db.oauth2_tokens.getIndexes()

# Verify TTL indexes on expires_at fields
# These auto-delete expired OAuth2 tokens and authorization codes
# No manual cleanup required
db.oauth2_tokens.getIndexes()      # Should show TTL on expires_at
db.oauth2_authorization_codes.getIndexes()  # Should show TTL on expires_at
```

### TTL Index Details

MongoDB automatically deletes documents when `expires_at` timestamp is reached:

- **oauth2_tokens** TTL index: Removes expired access/refresh tokens
- **oauth2_authorization_codes** TTL index: Removes expired auth codes (10-min window)
- No background job or cleanup script needed — MongoDB handles automatically

---

## Monitoring & Metrics

### Key Metrics

| Metric | Alert Threshold | Impact |
|--------|-----------------|--------|
| Request latency (p95) | >1000ms | Performance degradation |
| Error rate (5xx) | >1% | Service reliability |
| Failed logins | >100/hour | Possible attack |
| Database latency | >500ms | Database bottleneck |
| Redis latency | >100ms | Cache bottleneck |

### Health Endpoint

```bash
# Kubernetes liveness probe
curl -f http://localhost:8000/health || exit 1

# Load balancer health check
# Configure target group to check /health endpoint
```

---

## Troubleshooting

### MongoDB Connection Timeout

```bash
# Verify MongoDB running
docker ps | grep mongo

# Test connection
mongosh "mongodb://localhost:27017"

# Check firewall
telnet localhost 27017
```

### Redis Connection Refused

```bash
# Verify Redis running
docker ps | grep redis

# Test connection
redis-cli ping

# Check config
redis-cli CONFIG GET port
```

### Slow Login Times

```bash
# Check database latency
docker exec mongodb mongosh --eval "db.users.findOne()"

# Check Redis latency
redis-cli --latency

# Check app logs
docker logs -f auth-system | grep "latency\|slow"
```

### Email Not Sending

```bash
# Verify SMTP config
telnet smtp.example.com 587

# Check app logs
docker logs auth-system | grep "SMTP\|email"
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-03-29 | docs-manager | Initial deployment guide for v0.1.0 |
| 0.2.0 | 2026-03-31 | docs-manager | Updated: JWT_SECRET_KEY required, CORS_ORIGINS env var, Docker non-root user, audit log monitoring |
