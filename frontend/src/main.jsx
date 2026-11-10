import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [file, setFile] = useState(null);
  const [video, setVideo] = useState(null);
  const [start, setStart] = useState('0');
  const [duration, setDuration] = useState('10');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Choose a video to begin editing.');

  async function upload() {
    if (!file) return;
    setBusy(true); setMessage('Uploading video…');
    try {
      const data = new FormData(); data.append('file', file);
      const res = await fetch(`${API}/api/upload`, { method: 'POST', body: data });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Upload failed');
      setVideo(body); setMessage('Video ready. Set your trim points and export.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  async function exportTrim() {
    if (!video) return;
    setBusy(true); setMessage('Rendering your edit…');
    try {
      const res = await fetch(`${API}/api/export/trim`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ filename: video.filename, start: Number(start), duration: Number(duration) }) });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Export failed');
      setVideo({ ...body, original_name: 'Edited export' });
      setMessage('Your edited video is ready.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  return <main className="shell">
    <header><div className="brand"><span className="orb">J</span><div><p className="eyebrow">PERSONAL CREATIVE ASSISTANT</p><h1>JARVIS <em>VIDEO STUDIO</em></h1></div></div><span className="status"><i /> EDITOR READY</span></header>
    <section className="hero"><p className="eyebrow">YOUR IDEAS. YOUR EDIT.</p><h2>Make every second<br/><em>count.</em></h2><p className="sub">A mobile-friendly video editing workspace. Upload a clip, trim it, and export your edit.</p></section>
    <section className="workspace">
      <div className="panel preview"><div className="panel-head"><span>01 / PREVIEW</span><span>LIVE CANVAS</span></div>
        {video ? <video controls src={`${API}${video.url}`} /> : <label className="drop"><input type="file" accept="video/*" onChange={e => setFile(e.target.files?.[0] || null)} /><span className="upload-icon">＋</span><strong>{file ? file.name : 'Choose your video'}</strong><small>MP4, MOV, MKV, WEBM or AVI</small></label>}
        {video && <button className="quiet" onClick={() => { setVideo(null); setFile(null); }}>Choose another video</button>}
      </div>
      <div className="panel controls"><div className="panel-head"><span>02 / EDIT TOOLS</span><span>QUICK CUT</span></div><h3>Trim your clip</h3><p className="hint">Choose where the clip starts and how long the exported video should be.</p>
        <label>START TIME <div className="input-wrap"><input type="number" min="0" step="0.1" value={start} onChange={e => setStart(e.target.value)} /><span>seconds</span></div></label>
        <label>DURATION <div className="input-wrap"><input type="number" min="0.1" max="3600" step="0.1" value={duration} onChange={e => setDuration(e.target.value)} /><span>seconds</span></div></label>
        <button className="primary" disabled={!video || busy} onClick={exportTrim}>{busy ? 'WORKING…' : '✦  EXPORT VIDEO'}</button>
        <p className="notice">{message}</p>
      </div>
    </section>
    <footer><span>J.A.R.V.I.S. · VIDEO STUDIO</span><span>BUILT FOR CREATORS</span></footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
