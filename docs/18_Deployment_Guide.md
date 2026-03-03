# Deployment Guide — Local Pseudonymization Tool (Phase 4)

**Autore:** Team Engineering  
**Versione:** 4.1.0 (Phase 4)  
**Data:** 2026-03-02

---

## 1. Overview

This guide provides comprehensive instructions for deploying the Local Pseudonymization Tool with Phase 4 async architecture (Celery + Redis) in production environments.

**Deployment Modes:**
- **Docker Compose** (Recommended) — Single-host with multiple services
- **Kubernetes** — Multi-host orchestration with auto-scaling
- **Systemd Services** — Bare-metal deployment on Linux

---

## 2. Prerequisites

### Hardware Requirements

**Minimum (Development):**
- CPU: 2 cores
- RAM: 4 GB
- Disk: 20 GB free (for uploads/outputs)

**Recommended (Production):**
- CPU: 4+ cores
- RAM: 8+ GB (2 GB per Celery worker recommended)
- Disk: 100+ GB SSD (fast I/O for document processing)

### Software Requirements

**Required:**
- Docker 20.10+ and Docker Compose 2.0+ (for Docker deployment)
- Python 3.12+ (for bare-metal deployment)
- Redis 7.0+ (message broker + result backend)
- Tesseract OCR 4.0+ (for image parsing)

**Optional:**
- Kubernetes 1.24+ (for K8s deployment)
- PostgreSQL 14+ (alternative to SQLite for multi-worker setups)
- Flower (Celery monitoring web UI)
- Prometheus + Grafana (metrics and alerting)

---

## 3. Docker Compose Deployment (Recommended)

### 3.1. Quick Start

```bash
# Clone repository
git clone https://github.com/3n1gm496/pseudonymization-tool.git
cd pseudonymization-tool

# Configure environment variables (see section 3.2)
cp .env.example .env
nano .env  # Adjust settings

# Start all services
docker compose up -d

# Verify services
docker compose ps
docker compose logs -f backend
```

**Services Started:**
- `backend`: FastAPI app (port 8000)
- `redis`: Message broker (port 6379)
- `celery-worker`: Background task processor

**Access:**
- Application: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/api/health`

### 3.2. Environment Configuration

Create `.env` file in project root:

```bash
# Backend API
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
LOG_LEVEL=info  # debug|info|warning|error|critical

# Async Processing (Phase 4)
CELERY_BROKER_URL=redis://redis:6379/0
REDIS_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=${REDIS_URL}

# Security (CHANGE IN PRODUCTION!)
JWT_SECRET_KEY=your-super-secret-key-change-this-in-production-min-32-chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Database
DATABASE_URL=sqlite:///./data/batches.db  # Or PostgreSQL

# Storage Paths
UPLOAD_DIR=/app/uploads
OUTPUT_DIR=/app/outputs
PSEUDONYMIZER_STATE_DIR=/tmp/pseudonymizer_batches/state

# Celery Worker Settings
CELERY_WORKER_CONCURRENCY=4  # Tasks per worker
CELERY_WORKER_MAX_TASKS_PER_CHILD=100  # Restart after N tasks (memory leak prevention)
CELERY_TASK_TIME_LIMIT=3600  # 1 hour hard timeout
CELERY_TASK_SOFT_TIME_LIMIT=3300  # 55 min soft timeout

# Redis Configuration
REDIS_MAXMEMORY=256mb
REDIS_MAXMEMORY_POLICY=allkeys-lru
```

### 3.3. Docker Compose Configuration

```yaml
# docker-compose.yml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: pseudonymizer-backend
    ports:
      - "8000:8000"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - DATABASE_URL=${DATABASE_URL}
      - LOG_LEVEL=${LOG_LEVEL:-info}
    volumes:
      - ./backend/config:/app/config:ro
      - uploads:/app/uploads
      - outputs:/app/outputs
      - batch_data:/tmp/pseudonymizer
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: pseudonymizer-redis
    command: >
      redis-server
      --maxmemory ${REDIS_MAXMEMORY:-256mb}
      --maxmemory-policy ${REDIS_MAXMEMORY_POLICY:-allkeys-lru}
      --appendonly yes
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    restart: unless-stopped

  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: pseudonymizer-worker
    command: >
      celery -A app.core.tasks worker
      --loglevel=${LOG_LEVEL:-info}
      --concurrency=${CELERY_WORKER_CONCURRENCY:-4}
      --max-tasks-per-child=${CELERY_WORKER_MAX_TASKS_PER_CHILD:-100}
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=${DATABASE_URL}
      - LOG_LEVEL=${LOG_LEVEL:-info}
    volumes:
      - ./backend/config:/app/config:ro
      - uploads:/app/uploads
      - outputs:/app/outputs
      - batch_data:/tmp/pseudonymizer
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "celery", "-A", "app.core.tasks", "inspect", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  # Optional: Flower (Celery Monitoring UI)
  flower:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: pseudonymizer-flower
    command: celery -A app.core.tasks flower --port=5555
    ports:
      - "5555:5555"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
      - celery-worker
    restart: unless-stopped

volumes:
  redis_data:
  uploads:
  outputs:
  batch_data:
```

### 3.4. Scaling Workers

```bash
# Scale to 4 workers
docker compose up -d --scale celery-worker=4

# Verify workers
docker compose ps | grep celery-worker

# Monitor worker logs
docker compose logs -f celery-worker
```

### 3.5. Useful Commands

```bash
# View logs
docker compose logs -f backend       # Backend API logs
docker compose logs -f celery-worker # Worker logs
docker compose logs -f redis         # Redis logs

# Restart services
docker compose restart backend
docker compose restart celery-worker

# Execute commands in containers
docker compose exec backend bash
docker compose exec redis redis-cli

# Database migrations (if using PostgreSQL)
docker compose exec backend alembic upgrade head

# Cleanup
docker compose down -v  # Stop and remove volumes (DESTRUCTIVE!)
```

---

## 4. Kubernetes Deployment

### 4.1. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Ingress Controller                   │
│              (NGINX or Traefik with TLS)                │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼────────────────────────────────┐
│                  Backend Service (ClusterIP)            │
│                  Replicas: 2-4 (auto-scale)             │
└────────────┬──────────────────────────┬─────────────────┘
             │                          │
┌────────────▼──────────┐   ┌──────────▼─────────────────┐
│   Redis Service        │   │  Celery Worker Deployment  │
│   (StatefulSet)        │   │  Replicas: 3-6 (auto-scale)│
│   Persistent Volume    │   │  CPU/Memory limits         │
└────────────────────────┘   └────────────────────────────┘
```

### 4.2. Namespace and ConfigMap

```bash
# Create namespace
kubectl create namespace pseudonymizer

# Create ConfigMap
kubectl apply -f k8s/configmap.yaml
```

**k8s/configmap.yaml:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pseudonymizer-config
  namespace: pseudonymizer
data:
  BACKEND_HOST: "0.0.0.0"
  BACKEND_PORT: "8000"
  LOG_LEVEL: "info"
  CELERY_BROKER_URL: "redis://redis-service:6379/0"
  REDIS_URL: "redis://redis-service:6379/0"
  DATABASE_URL: "postgresql://user:pass@postgres-service:5432/pseudonymizer"
  CELERY_WORKER_CONCURRENCY: "4"
  CELERY_WORKER_MAX_TASKS_PER_CHILD: "100"
```

### 4.3. Secrets

```bash
# Create secrets
kubectl create secret generic pseudonymizer-secrets \
  --from-literal=jwt-secret-key='your-super-secret-key-min-32-chars' \
  -n pseudonymizer
```

### 4.4. Redis StatefulSet

**k8s/redis-statefulset.yaml:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: redis-service
  namespace: pseudonymizer
spec:
  ports:
    - port: 6379
      targetPort: 6379
  selector:
    app: redis
  clusterIP: None  # Headless service for StatefulSet

---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis
  namespace: pseudonymizer
spec:
  serviceName: redis-service
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        command: ["redis-server"]
        args:
          - "--maxmemory"
          - "512mb"
          - "--maxmemory-policy"
          - "allkeys-lru"
          - "--appendonly"
          - "yes"
        ports:
        - containerPort: 6379
          name: redis
        volumeMounts:
        - name: redis-data
          mountPath: /data
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
  volumeClaimTemplates:
  - metadata:
      name: redis-data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 10Gi
```

### 4.5. Backend Deployment

**k8s/backend-deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: pseudonymizer
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
      - name: backend
        image: pseudonymizer-backend:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: pseudonymizer-config
        env:
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: pseudonymizer-secrets
              key: jwt-secret-key
        volumeMounts:
        - name: config
          mountPath: /app/config
          readOnly: true
        - name: uploads
          mountPath: /app/uploads
        - name: outputs
          mountPath: /app/outputs
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /api/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/ready
            port: 8000
          initialDelaySeconds: 20
          periodSeconds: 5
      volumes:
      - name: config
        configMap:
          name: pseudonymizer-config-files
      - name: uploads
        emptyDir: {}
      - name: outputs
        emptyDir: {}

---
apiVersion: v1
kind: Service
metadata:
  name: backend-service
  namespace: pseudonymizer
spec:
  type: ClusterIP
  ports:
  - port: 8000
    targetPort: 8000
  selector:
    app: backend
```

### 4.6. Celery Worker Deployment

**k8s/worker-deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker
  namespace: pseudonymizer
spec:
  replicas: 3
  selector:
    matchLabels:
      app: celery-worker
  template:
    metadata:
      labels:
        app: celery-worker
    spec:
      containers:
      - name: worker
        image: pseudonymizer-backend:latest
        command: ["celery"]
        args:
          - "-A"
          - "app.core.tasks"
          - "worker"
          - "--loglevel=info"
          - "--concurrency=4"
          - "--max-tasks-per-child=100"
        envFrom:
        - configMapRef:
            name: pseudonymizer-config
        volumeMounts:
        - name: config
          mountPath: /app/config
          readOnly: true
        - name: uploads
          mountPath: /app/uploads
        - name: outputs
          mountPath: /app/outputs
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          exec:
            command: ["celery", "-A", "app.core.tasks", "inspect", "ping"]
          initialDelaySeconds: 30
          periodSeconds: 30
      volumes:
      - name: config
        configMap:
          name: pseudonymizer-config-files
      - name: uploads
        emptyDir: {}
      - name: outputs
        emptyDir: {}
```

### 4.7. Horizontal Pod Autoscaler (HPA)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: celery-worker-hpa
  namespace: pseudonymizer
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: celery-worker
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### 4.8. Ingress (NGINX)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: pseudonymizer-ingress
  namespace: pseudonymizer
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  rules:
  - host: pseudonymizer.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: backend-service
            port:
              number: 8000
  tls:
  - hosts:
    - pseudonymizer.example.com
    secretName: pseudonymizer-tls
```

---

## 5. Systemd Deployment (Bare-Metal)

### 5.1. Installation

```bash
# Install Python 3.12+
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip

# Install Redis
sudo apt install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Install Tesseract OCR
sudo apt install -y tesseract-ocr tesseract-ocr-eng

# Clone repository
cd /opt
sudo git clone https://github.com/3n1gm496/pseudonymization-tool.git
cd pseudonymization-tool

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

### 5.2. System User

```bash
# Create service user
sudo useradd -r -s /bin/false pseudonymizer
sudo chown -R pseudonymizer:pseudonymizer /opt/pseudonymization-tool
```

### 5.3. Environment Configuration

```bash
# Create environment file
sudo nano /etc/pseudonymizer/environment

# Add:
CELERY_BROKER_URL=redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-super-secret-key-change-in-production
DATABASE_URL=sqlite:////var/lib/pseudonymizer/batches.db
LOG_LEVEL=info
UPLOAD_DIR=/var/lib/pseudonymizer/uploads
OUTPUT_DIR=/var/lib/pseudonymizer/outputs
```

### 5.4. Systemd Service - Backend

**File:** `/etc/systemd/system/pseudonymizer-backend.service`

```ini
[Unit]
Description=Pseudonymizer Backend API
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=pseudonymizer
Group=pseudonymizer
WorkingDirectory=/opt/pseudonymization-tool/backend
EnvironmentFile=/etc/pseudonymizer/environment
ExecStart=/opt/pseudonymization-tool/venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 5.5. Systemd Service - Celery Worker

**File:** `/etc/systemd/system/pseudonymizer-worker.service`

```ini
[Unit]
Description=Pseudonymizer Celery Worker
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=pseudonymizer
Group=pseudonymizer
WorkingDirectory=/opt/pseudonymization-tool/backend
EnvironmentFile=/etc/pseudonymizer/environment
ExecStart=/opt/pseudonymization-tool/venv/bin/celery \
    -A app.core.tasks worker \
    --loglevel=info \
    --concurrency=4 \
    --max-tasks-per-child=100
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 5.6. Enable and Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable pseudonymizer-backend
sudo systemctl enable pseudonymizer-worker

# Start services
sudo systemctl start pseudonymizer-backend
sudo systemctl start pseudonymizer-worker

# Check status
sudo systemctl status pseudonymizer-backend
sudo systemctl status pseudonymizer-worker

# View logs
sudo journalctl -u pseudonymizer-backend -f
sudo journalctl -u pseudonymizer-worker -f
```

---

## 6. Monitoring and Observability

### 6.1. Flower (Celery Monitoring)

```bash
# Docker Compose
docker compose up -d flower

# Access: http://localhost:5555
```

**Features:**
- Real-time task monitoring
- Worker statistics
- Task history and traces
- Task retry/cancel controls

### 6.2. Prometheus Metrics

**Install Prometheus exporter:**

```bash
pip install prometheus-client
pip install celery-exporter
```

**Start exporter:**

```bash
celery-exporter --broker-url=redis://localhost:6379/0 --port=9540
```

**Prometheus scrape config:**

```yaml
scrape_configs:
  - job_name: 'celery'
    static_configs:
      - targets: ['localhost:9540']
  
  - job_name: 'backend'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
```

### 6.3. Key Metrics to Monitor

**Backend API:**
- Request rate (req/sec)
- Response time (p50, p95, p99)
- Error rate (4xx, 5xx)
- Active sessions

**Celery Workers:**
- Task throughput (tasks/sec)
- Task duration (avg, p95)
- Active tasks
- Failed tasks
- Worker pool utilization

**Redis:**
- Memory usage
- Key count
- Queue length
- Eviction rate

**System:**
- CPU usage (per service)
- Memory usage (per service)
- Disk I/O (uploads/outputs)
- Network traffic

---

## 7. Security Hardening

### 7.1. JWT Secret Rotation

```bash
# Generate new secret
openssl rand -base64 32

# Update .env or secrets
JWT_SECRET_KEY=new-generated-secret-key

# Restart backend
docker compose restart backend
# OR
sudo systemctl restart pseudonymizer-backend
```

### 7.2. TLS/SSL Configuration

**NGINX Reverse Proxy:**

```nginx
server {
    listen 443 ssl http2;
    server_name pseudonymizer.example.com;

    ssl_certificate /etc/letsencrypt/live/pseudonymizer.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pseudonymizer.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 7.3. Firewall Rules

```bash
# Allow only necessary ports
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 443/tcp   # HTTPS
sudo ufw deny 8000/tcp   # Block direct access to backend
sudo ufw deny 6379/tcp   # Block direct access to Redis
sudo ufw enable
```

### 7.4. Redis Security

```bash
# Edit Redis config
sudo nano /etc/redis/redis.conf

# Add:
requirepass your-redis-password
bind 127.0.0.1  # Only localhost
protected-mode yes
```

---

## 8. Backup and Recovery

### 8.1. Database Backup (SQLite)

```bash
# Backup
sqlite3 /var/lib/pseudonymizer/batches.db ".backup /backups/batches_$(date +%Y%m%d).db"

# Automated backup (cron)
0 2 * * * /usr/bin/sqlite3 /var/lib/pseudonymizer/batches.db ".backup /backups/batches_$(date +\%Y\%m\%d).db"
```

### 8.2. Redis Backup

```bash
# Manual backup
redis-cli SAVE
cp /var/lib/redis/dump.rdb /backups/redis_$(date +%Y%m%d).rdb

# Automated backup (cron)
0 3 * * * redis-cli SAVE && cp /var/lib/redis/dump.rdb /backups/redis_$(date +\%Y\%m\%d).rdb
```

### 8.3. Application Files Backup

```bash
# Backup uploads and outputs
tar -czf /backups/pseudonymizer_data_$(date +%Y%m%d).tar.gz \
    /var/lib/pseudonymizer/uploads \
    /var/lib/pseudonymizer/outputs
```

---

## 9. Troubleshooting

### 9.1. Backend Not Starting

**Check logs:**
```bash
docker compose logs backend
# OR
sudo journalctl -u pseudonymizer-backend -n 50
```

**Common issues:*
- Missing environment variables
- Port 8000 already in use
- Database connection failure
- Redis connection failure

**Fix:**
```bash
# Check port usage
sudo netstat -tulpn | grep 8000

# Test Redis connection
redis-cli ping

# Verify environment
docker compose exec backend env | grep CELERY
```

### 9.2. Tasks Not Processing

**Check Celery worker:**
```bash
docker compose logs celery-worker
# OR
sudo journalctl -u pseudonymizer-worker -n 50
```

**Common issues:**
- Redis connection failure
- Task timeout
- Memory exhaustion
- Worker crashed

**Fix:**
```bash
# Check Redis connectivity from worker
docker compose exec celery-worker redis-cli -h redis ping

# Check worker status
docker compose exec celery-worker celery -A app.core.tasks inspect active

# Restart worker
docker compose restart celery-worker
```

### 9.3. Redis Out of Memory

**Symptoms:**
- Tasks failing with Redis OOM errors
- Eviction warnings in logs

**Fix:**
```bash
# Check Redis memory usage
redis-cli INFO memory

# Increase maxmemory limit
docker compose down
# Edit docker-compose.yml: REDIS_MAXMEMORY=512mb
docker compose up -d

# Clear old task results
redis-cli --scan --pattern "celery-task-meta-*" | xargs redis-cli DEL
```

### 9.4. Slow Scan Performance

**Check:**
- Worker concurrency setting
- Number of active workers
- System resource usage (CPU, RAM, disk I/O)

**Optimize:**
```bash
# Increase worker concurrency
CELERY_WORKER_CONCURRENCY=8 docker compose up -d

# Scale to more workers
docker compose up -d --scale celery-worker=4

# Monitor task duration
docker compose exec celery-worker celery -A app.core.tasks inspect stats
```

---

## 10. Production Checklist

### Pre-Deployment

- [ ] Change `JWT_SECRET_KEY` to strong random value
- [ ] Configure TLS/SSL certificates
- [ ] Set up firewall rules
- [ ] Configure log rotation
- [ ] Set up monitoring (Prometheus + Grafana)
- [ ] Configure automated backups
- [ ] Test disaster recovery procedure
- [ ] Document environment-specific settings

### Post-Deployment

- [ ] Verify health checks (`/api/health`, `/api/ready`)
- [ ] Test full scan workflow (text + file upload)
- [ ] Verify async task processing
- [ ] Check Celery worker logs for errors
- [ ] Monitor Redis memory usage
- [ ] Set up alerting rules (disk space, memory, errors)
- [ ] Create runbook for common issues
- [ ] Train operations team on monitoring/troubleshooting

### Security

- [ ] Enable Redis authentication
- [ ] Restrict Redis to localhost/internal network
- [ ] Use strong JWT secret (min 32 chars)
- [ ] Enable HTTPS only (redirect HTTP → HTTPS)
- [ ] Implement rate limiting (already included)
- [ ] Regular security updates (Docker images, Python packages)
- [ ] Audit logging for sensitive operations

---

## 11. Performance Tuning

### 11.1. Worker Optimization

```bash
# Increase concurrency for CPU-bound tasks
CELERY_WORKER_CONCURRENCY=8

# Use prefork pool (default, good for I/O)
celery -A app.core.tasks worker --pool=prefork

# Use gevent pool for high-concurrency I/O
# pip install gevent
# celery -A app.core.tasks worker --pool=gevent --concurrency=100
```

### 11.2. Redis Optimization

```conf
# /etc/redis/redis.conf
maxmemory 1gb
maxmemory-policy allkeys-lru
save ""  # Disable RDB snapshots for pure cache
appendonly no  # Disable AOF for performance
```

### 11.3. Database Optimization

**Switch to PostgreSQL for production:**

```python
# .env
DATABASE_URL=postgresql://user:pass@localhost:5432/pseudonymizer

# Install driver
pip install psycopg2-binary

# Run migrations
alembic upgrade head
```

---

## 12. Scaling Guidelines

### Single Host (Docker Compose)

- **Small** (1-10 concurrent users): 1 worker, 2 GB RAM
- **Medium** (10-50 concurrent users): 2-4 workers, 8 GB RAM
- **Large** (50-100 concurrent users): 4-8 workers, 16 GB RAM

### Multi-Host (Kubernetes)

- **Workers**: 1 pod per 2 GB RAM available
- **Backend**: 2-4 replicas (stateless, easy to scale)
- **Redis**: 1-3 replicas (StatefulSet with replication)

**Auto-scaling formula:**
```
Workers needed = (Peak concurrent scans × Avg scan duration) / Worker concurrency
```

Example:
- Peak: 20 scans/minute
- Avg duration: 120 seconds
- Concurrency: 4 tasks/worker

Workers = (20 × 2 minutes) / 4 = 10 workers minimum

---

## 13. Support and Resources

**Documentation:**
- Technical Architecture: [docs/02_Technical_Architecture.md](02_Technical_Architecture.md)
- Data Model: [docs/03_Data_Model.md](03_Data_Model.md)
- API Reference: http://localhost:8000/docs

**Monitoring:**
- Flower UI: http://localhost:5555 (if enabled)
- Prometheus metrics: http://localhost:9540/metrics (if exporter installed)

**Community:**
- GitHub Issues: https://github.com/3n1gm496/pseudonymization-tool/issues
- Discussions: https://github.com/3n1gm496/pseudonymization-tool/discussions

---

**Last Updated:** 2026-03-02 (Phase 4)  
**Version:** 4.1.0
