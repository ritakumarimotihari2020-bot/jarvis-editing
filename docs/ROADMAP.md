# JARVIS Video Studio roadmap

## MVP scaffold
- Responsive React/Vite editor interface
- FastAPI health and upload endpoints
- FFmpeg trim/export endpoint
- Docker image with FFmpeg installed

## Next milestones
1. Add timeline with multiple clips and draggable trim handles.
2. Add text overlays, subtitle tracks, transitions, and audio mixing.
3. Add speech-to-text captions (Whisper) and Hindi/English command parsing.
4. Add project persistence and background export jobs.
5. Package the mobile-friendly client as an Android app (Capacitor) after the web workflow is stable.

## Current limitations
This is an initial working scaffold, not a complete AI editor. AI scene detection, auto-captions, multi-track editing, authentication, and Android APK packaging are not implemented yet. The API requires FFmpeg on the server for exports.
