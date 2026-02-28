# Frontend React Setup Instructions

## Dev Environment

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173

## Build for Production

```bash
npm run build
```

This creates `dist/` folder that FastAPI will serve.

## Features

✓ Modern React 18 with Vite
✓ Tailwind CSS with dark mode support
✓ Responsive mobile-first design
✓ Toast notifications
✓ Real-time policy preview
✓ Drag-and-drop file upload
✓ Smooth animations and transitions
✓ Accessibility (WCAG A compliance planned)

## File Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── Header.jsx
│   │   ├── Scanner.jsx
│   │   ├── PolicySelector.jsx
│   │   ├── FindingsTable.jsx
│   │   └── Results.jsx
│   ├── context/
│   │   └── ThemeContext.jsx
│   ├── hooks/
│   │   └── useToast.jsx
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css
├── index.html
├── package.json
├── vite.config.js
├── tailwind.config.js
└── postcss.config.js
```

## Backend Integration

The backend (FastAPI) will serve the built React app from `dist/` folder in production.

For development, use the Vite dev server with proxy to http://127.0.0.1:8000/api/*
