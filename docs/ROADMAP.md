# JARVIS AI Video Studio — roadmap

## Implemented in 0.6.0
- Per-clip timeline IN/OUT trim values with duration-aware validation
- Timeline export applies each clip trim before normalizing and joining clips

## Previously implemented in 0.5.0
- Multi-clip timeline: upload up to 20 clips, reorder them, remove clips, and export a single MP4
- Timeline export normalizes video size, frame rate, pixel format, and audio track before joining clips

## Previously implemented in 0.4.1
- Responsive React/Vite editor interface
- FastAPI upload, health, and FFprobe metadata endpoints
- FFmpeg trim/export with backend and frontend trim-range validation
- Video-player playhead controls to set trim start and end points
- Browser speech recognition controls for Hindi/English trim and export commands
- Optional Whisper-powered Hindi/English/auto speech-to-text captions as downloadable SRT
- SRT caption text preview in the editor
- FFmpeg subtitle burn-in export to a new MP4 file
- Docker image with FFmpeg/FFprobe installed

## Enable AI auto-captions
Install the base backend requirements, then install `backend/requirements-ai.txt`.
The first caption request downloads Whisper's `base` model, so the server needs internet access and enough RAM/disk. CPU transcription can be slow. Voice commands use browser Web Speech API and require a supported browser (Chrome on Android is recommended) and microphone permission.

## Next milestones
1. Add draggable visual trim handles and continuous timeline preview playback.
2. Add text overlays, transitions, and audio mixing.
3. Add project persistence and background export jobs.
4. Add automated backend/frontend tests and deployment configuration.
5. Package the mobile-friendly client as an Android app (Capacitor) after the web workflow is stable.

## Current limitations
This is an early editor scaffold, not a full AI editor. The multi-clip timeline supports ordering, per-clip numeric IN/OUT trims, and joining; draggable visual handles and continuous timeline preview are not implemented yet. Voice recognition depends on browser support. Whisper captions are optional and are not ready until the AI requirements and model are installed on the server. Subtitle burn-in requires FFmpeg with the subtitles/libass filter available. APK packaging, authentication, and cloud deployment are not implemented yet. The API needs FFmpeg and FFprobe on the server. Runtime/build tests have not yet been run for this increment.
