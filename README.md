# JARVIS AI Video Studio

A dedicated, mobile-friendly video editing project. Existing desktop assistant projects are kept separate and untouched.

## Repository layout
- `backend/` — FastAPI API and FFmpeg media processing
- `frontend/` — responsive React/Vite editor
- `docs/` — roadmap and implementation notes

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
# Activate the environment, then:
pip install -r requirements.txt
# Install FFmpeg and ensure `ffmpeg` is on PATH.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to `http://localhost:8000` for the API. Set `VITE_API_URL` when the backend is hosted elsewhere.

## Current MVP
- Upload and preview common video formats
- Trim a clip by start time and duration
- Export MP4 using FFmpeg

This is an initial scaffold, not yet a complete AI editor or installable APK. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for planned AI and Android milestones.
