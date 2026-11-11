# Ayansh Hosting — Minecraft Panel

A responsive frontend prototype for a Minecraft server hosting dashboard.

## Preview locally
Open `index.html` in a browser, or serve this directory with any static web server.

## Publish with GitHub Pages
In the repository, open **Settings → Pages**. Choose **Deploy from a branch**, select **main**, and set the folder to **/ (root)** only if you move this site's files to the repository root. For this current folder layout, use GitHub Actions or configure a Pages workflow whose artifact is the `hosting-panel` directory.

## Important: demo only
The Start, Stop and Restart buttons currently simulate status in the browser. Console, player counts, RAM, files, plugins, backups and server creation are not connected to a Minecraft server. A secure backend/agent and a persistent host machine are required for real server control and 24/7 uptime. Never expose a host machine's shell or panel API directly to an unauthenticated browser.

## Planned backend
- Authenticated API with owner/admin roles
- Per-server isolated process/container management
- Paper/Spigot and Java/Bedrock (Geyser) configuration
- WebSocket console stream
- File/plugin management with strict path validation
- Resource metrics, backups and audit logs
