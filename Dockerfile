# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1: Build React Frontend with Node.js
# ═══════════════════════════════════════════════════════════════════════════════

FROM node:20-alpine AS frontend-builder

LABEL stage=builder description="Builds React frontend with Vite"

WORKDIR /build/frontend

# Copy package files
COPY frontend/package*.json ./

# ✅ FIX #19: Use npm install with explicit omit for dev dependencies
# This generates package-lock.json automatically if missing
RUN npm install --omit=dev && \
    npm install --save-dev vite @vitejs/plugin-react tailwindcss postcss autoprefixer && \
    echo "✓ Node packages installed"

# Copy source
COPY frontend/src ./src
COPY frontend/index.html ./
COPY frontend/vite.config.js ./
COPY frontend/tailwind.config.js ./
COPY frontend/postcss.config.js ./
COPY frontend/tsconfig.json ./

# Build React app with Vite
RUN npm run build

# ═══════════════════════════════════════════════════════════════════════════════
# Stage 2: Runtime - Python Backend with FastAPI + Built Frontend
# ═══════════════════════════════════════════════════════════════════════════════

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend

LABEL maintainer="Pseudonymization Tool" \
      version="4.0" \
      description="Self-contained pseudonymization service with React UI"

# Install system dependencies (Tesseract OCR, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-ita \
    tesseract-ocr-eng \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-cache policy tesseract-ocr \
    && echo "✓ System packages installed successfully"

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt && \
    echo "✓ Python packages installed successfully"

# Copy backend application
COPY backend /app/backend

# Copy frontend dist from builder stage
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

# Verify frontend was built
RUN test -f /app/frontend/dist/index.html || (echo "ERROR: Frontend build failed" && exit 1) && \
    echo "✓ Frontend: $(ls -la /app/frontend/dist | grep -c '\.')-1 files"

WORKDIR /app/backend

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health > /dev/null || exit 1

# Startup message + run app
CMD echo "🚀 Pseudonymization Tool v4.0 started" && \
    echo "📍 Backend: http://0.0.0.0:8000" && \
    echo "📍 Frontend: http://0.0.0.0:8000 (served by backend)" && \
    echo "🔒 Offline mode: All processing happens locally" && \
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
