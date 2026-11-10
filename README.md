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


## Android app (Capacitor)

The React editor can be wrapped in a native Android shell while the FastAPI/FFmpeg backend remains hosted separately.

1. Install Node.js 20+, Java 17, and Android Studio with an Android SDK.
2. In `frontend/`, install dependencies with `npm install`.
3. Copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_URL` to the public **HTTPS** URL of your running FastAPI backend. Do not use `localhost` in an Android build; on the phone, localhost points to the phone itself.
4. Build the web assets with `npm run build:mobile`.
5. Add the Android platform once with `npx cap add android`.
6. Copy web assets and native plugin configuration with `npm run cap:sync`.
7. Open Android Studio with `npm run cap:open:android`, then build an APK using **Build → Build Bundle(s) / APK(s) → Build APK(s)**.

The generated native `frontend/android/` project is local build output and is not committed by this setup. The APK still needs a reachable backend URL, Android signing for release distribution, and device testing. This repository change does not itself create or install an APK.


## Automated Android APK build (GitHub Actions)

The `JARVIS Android APK` workflow builds a debug APK on changes to `frontend/` on the development branch, or when manually started from the Actions tab. Before running it, you may add a repository variable named `VITE_API_URL` under **Settings → Secrets and variables → Actions → Variables**, or manually start the workflow and enter the public HTTPS FastAPI URL in its `api_url` input. If neither is provided, the workflow uses a placeholder HTTPS URL so that the APK build can proceed; backend-dependent features will not connect until you rebuild with your real public HTTPS FastAPI URL. Non-HTTPS values are rejected. When the workflow succeeds, download `app-debug.apk` from its `jarvis-video-studio-debug-apk` artifact on the workflow run page. This is a debug APK, not a signed Play Store release; it still needs real-device testing.
