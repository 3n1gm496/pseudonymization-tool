#!/bin/bash
# Development script for Pseudonymization Tool - Full Stack

echo "🚀 Starting Pseudonymization Tool v4.0 (Full Stack)"
echo "===================================================="
echo ""
echo "Frontend:  http://localhost:5173 (Vite dev server with HMR)"
echo "Backend:   http://127.0.0.1:8000 (FastAPI)"
echo "API Proxy: /api/* -> http://127.0.0.1:8000"
echo ""
echo "Press Ctrl+C to stop both servers"
echo "===================================================="
echo ""

# Start backend in background
echo "📍 Starting backend (port 8000)..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT/backend"
source "$REPO_ROOT/.venv/bin/activate" 2>/dev/null || true
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

sleep 2

# Start frontend in background
echo "📍 Starting frontend (port 5173)..."
cd "$REPO_ROOT/frontend"
npm install 2>/dev/null || echo "Dependencies already installed"
npm run dev &
FRONTEND_PID=$!

sleep 2

echo ""
echo "✅ Both servers started!"
echo "   Backend  PID:  $BACKEND_PID"
echo "   Frontend PID:  $FRONTEND_PID"
echo ""

# Cleanup on exit
trap 'echo "Shutting down..."; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0' INT TERM

# Wait for both processes
wait
