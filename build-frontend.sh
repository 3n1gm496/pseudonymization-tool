#!/bin/bash
# Build script for Pseudonymization Tool - React Frontend

set -e

echo "🔨 Building React Frontend..."
echo "=================================="

cd "$(dirname "$0")/frontend"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Build the React app
echo "⚙️  Compiling React with Vite..."
npm run build

echo ""
echo "✅ Build completed successfully!"
echo "=================================="
echo ""
echo "Frontend built to: frontend/dist/"
echo "The backend will serve this in production mode."
echo ""
echo "To start the full stack:"
echo "  1. Backend: cd backend && python -m uvicorn app.main:app"
echo "  2. Frontend will be served at http://127.0.0.1:8000"
