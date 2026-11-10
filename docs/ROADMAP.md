# JARVIS AI Video Studio — roadmap

## Implemented in 0.19.0
- Added Capacitor core, Android platform and CLI dependencies plus mobile build/sync/open scripts
- Added Capacitor app configuration for the JARVIS Video Studio Android wrapper
- Improved mobile touch target sizes, safe-area spacing, timeline controls and export-history layout
- Documented Android Studio build steps and the requirement for a public HTTPS backend URL
- APK generation and device installation remain unverified and require a local Android SDK/Android Studio build

## Implemented in 0.18.0
- Added FFmpeg machine-readable progress output for the final multi-clip transition render
- Parse FFmpeg elapsed render time and update persistent export job progress up to 99%; mark 100% only after successful completion
- Keep cancellation and timeout handling active while FFmpeg progress is streamed
- Added regression coverage for FFmpeg progress timestamp parsing and bounds


## Implemented in 0.17.0
- Persisted the latest 100 export job records to `projects/export_jobs.json` using atomic file replacement
- Added timestamps and a history endpoint (`GET /api/export/jobs`)
- Added editor history refresh and links to completed export files
- On API startup, queued/running records are marked `interrupted` instead of falsely appearing active
- Added regression coverage for history persistence, restart recovery and history listing
- Persistence survives API process restarts when the project directory is retained; container replacement still requires a persistent volume

## Implemented in 0.16.0
- Added a cancel endpoint for queued/running transition export jobs
- FFmpeg normalization and final render subprocesses can now be terminated when cancellation is requested
- Added an editor cancel control and cancellation state feedback
- Added regression coverage for cancellation, completed-job conflict and unknown jobs
- Job records remain in process memory; progress remains phase-based rather than frame-accurate

## Implemented in 0.15.0
- Added background transition-export job submission with HTTP 202 responses
- Added export job status endpoint with queued, running, completed and failed states
- Connected the editor to poll job status and show export state/progress feedback
- Added regression tests for successful job completion, invalid IDs and missing jobs
- Job state is currently held in process memory; restarting the API clears active/history records and progress is phase-based, not FFmpeg frame-level


## Implemented in 0.14.0
- Added persistent project save, list, load and delete API endpoints
- Saved timeline clip order and trim points plus transition, text overlay, fade, music-volume and trim settings
- Added project name, save/update, refresh and load controls in the editor
- Added validation for project names, clip counts, clip file availability and trim ranges
- Added regression tests for project persistence and invalid project data


## Implemented in 0.13.0
- Added a separate timeline transition export API, preserving the original hard-cut export
- Added fade, dissolve, wipe, slide and circle-open video transitions with matching audio crossfades
- Normalizes clip dimensions, frame rate, pixel format and audio (including silent clips) before transition rendering
- Added transition style and duration controls to the multi-clip editor
- Added regression tests for invalid transition settings, short clips and generated FFmpeg filter graphs


## Implemented in 0.12.0
- Added FFmpeg fade-in and fade-out effects for video, with matching audio fades when an audio stream exists
- Added validation for negative, empty, and overlong combined fade durations
- Added editor sliders and MP4 export action for fade effects
- Added backend regression tests for fade validation and silent-video filter generation


## Implemented in 0.11.0
- Added text overlays with seven screen positions and adjustable font size
- Render text into MP4 using FFmpeg drawtext and a UTF-8 text file
- Added input validation tests and installed DejaVu fonts in the Docker image


## Implemented in 0.10.0
- Added background music upload for MP3, WAV, AAC, M4A, OGG and FLAC
- Added FFmpeg music mixing with independent original/music volume controls and loop-to-video duration
- Added validation and regression tests for unsupported audio uploads and volume bounds

## Implemented in 0.9.1
- Added an FFmpeg-powered audio waveform endpoint with bounded processing and compact amplitude samples
- Added a waveform preview to the video player panel, including handling for videos without audio
- Added a regression test for silent-video waveform responses

## Implemented in 0.9.0
- Added draggable IN/OUT trim handles to every multi-clip timeline row
- Kept numeric per-clip trim fields and synchronized them with the visual handles

## Implemented in 0.8.0
- Added a dual-handle visual trim range for the main video editor
- Drag either handle on desktop or touch screens to adjust the selected start and end points
- Kept numeric trim inputs and playhead controls available alongside the visual range
- Added five backend API regression tests and included pytest in the GitHub Actions workflow

## Previously implemented in 0.7.0
- Sequential timeline preview plays each clip in order and respects its IN/OUT trim points
- Timeline clip upload automatically selects the first clip for the preview player

## Previously implemented in 0.6.0
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

## Android APK build pipeline (0.20.0)
- Added a GitHub Actions workflow that generates the Capacitor Android project and builds a debug APK on pushes affecting the frontend, or on manual dispatch.
- The workflow requires the repository Actions variable `VITE_API_URL` to be set to a public HTTPS FastAPI endpoint; it fails early with a clear message when missing or invalid.
- The debug APK is uploaded as the `jarvis-video-studio-debug-apk` workflow artifact for 14 days.
- Release signing, backend hosting, and real-device verification remain outstanding.

## Next milestones
1. Add automated frontend tests and deployment configuration.
2. Sign a release APK and test the app on real Android devices.

## Current limitations
This is an early editor scaffold, not a full AI editor. The multi-clip timeline supports ordering, per-clip numeric IN/OUT trims, and joining; draggable visual handles are available for both the main single-video trim editor and each multi-clip timeline row; waveform preview is implemented for the main selected video; multi-clip per-row waveforms and audio mixing is implemented for the main selected video; multi-clip soundtrack mixing is not implemented yet. Voice recognition depends on browser support. Whisper captions are optional and are not ready until the AI requirements and model are installed on the server. Subtitle burn-in requires FFmpeg with the subtitles/libass filter available. APK packaging, authentication, and cloud deployment are not implemented yet. Fade and transition effects re-encode video and audio, so export time depends on source length and server CPU. Saved projects store references to uploaded media files; deleting those media files makes their project clips unavailable. Project storage currently has no user authentication or cloud synchronization. Saved projects store references to uploaded media files; deleting those media files makes their project clips unavailable. Project storage currently has no user authentication or cloud synchronization. The API needs FFmpeg and FFprobe on the server. Automated backend API tests are configured in GitHub Actions; frontend build and real video playback/export still need verification.
