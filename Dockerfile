# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1: Build React Frontend with Node.js
# ═══════════════════════════════════════════════════════════════════════════════

FROM node:20-alpine AS frontend-builder

LABEL stage=builder description="Builds React frontend with Vite"

WORKDIR /build/frontend

# Copy lock file and package manifest (enables deterministic installs with npm ci)
COPY frontend/package*.json ./

# Install ALL dependencies (dev included) needed for the Vite build, then build.
# devDependencies (vite, tailwindcss, etc.) are required at build time only;
# they are NOT copied into the runtime stage.
RUN npm ci && \
    echo "✓ Node packages installed (lock file respected)"

# Copy source
COPY frontend/src ./src
COPY frontend/index.html ./
COPY frontend/vite.config.js ./
COPY frontend/tailwind.config.js ./
COPY frontend/postcss.config.js ./
# Build React app with Vite
RUN npm run build && \
    echo "✓ Frontend built successfully"

# ═══════════════════════════════════════════════════════════════════════════════
# Stage 2: Runtime - Python Backend with FastAPI + Built Frontend
# ═══════════════════════════════════════════════════════════════════════════════

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend

LABEL maintainer="Pseudonymization Tool" \
      version="5.0.0" \
      description="Self-contained pseudonymization service with React UI"

# Install system dependencies (Tesseract OCR, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-ita \
    tesseract-ocr-eng \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for runtime security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Install Python dependencies using lock file for deterministic builds (as root, before switching user)
# Use requirements.lock for reproducible production builds;
# fall back to requirements.txt only if lock file is absent.
COPY backend/requirements.lock backend/requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.lock && \
    rm -f requirements.lock requirements.txt && \
    echo "✓ Python packages installed from lock file (deterministic build)"

# Copy backend application
COPY backend /app/backend

# Copy frontend dist from builder stage
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

# Verify frontend was built
RUN test -f /app/frontend/dist/index.html || \
    (echo "ERROR: Frontend build failed — dist/index.html missing" && exit 1) && \
    echo "✓ Frontend dist verified"

# Create writable directories for runtime state and give ownership to appuser
RUN mkdir -p /app/state /tmp/pseudonymizer_batches && \
    chown -R appuser:appgroup /app /tmp/pseudonymizer_batches

WORKDIR /app/backend

# Switch to non-root user
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health > /dev/null || exit 1

# Use exec form (no shell) for proper signal handling and clean process tree.
# PSEUDONYMIZER_HOST defaults to 127.0.0.1 in config.py; Docker sets it to
# 0.0.0.0 via the environment variable below so the container is reachable.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
