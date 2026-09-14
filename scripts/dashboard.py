#!/usr/bin/env python3
"""Web dashboard for fd-scraw-harness: view manifests, trigger approve/reject.

Usage:
    cd fd-scraw-harness
    uv run python scripts/dashboard.py [port]

    # → open http://127.0.0.1:8892

API endpoints:
    GET  /api/manifests               → list all manifests
    GET  /api/manifests/<id>          → single manifest detail (with YAML)
    GET  /api/discoveries             → list discovery sessions
    GET  /api/discoveries/<id>        → discovery detail with candidates
    POST /api/manifests/<id>/approve  → approve a draft manifest
    POST /api/manifests/<id>/reject   → reject a manifest
"""
from __future__ import annotations

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.chdir(_REPO_ROOT)

from fd_scraw_harness.db import init_db, get_session
from fd_scraw_harness.models import Discovery, Candidate, Analysis, Manifest

init_db()

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>fd-scraw-harness Dashboard</title>
<style>
:root { --bg:#f0f2f5; --card:#fff; --border:#e0e0e0; --text:#1a1a2e; --text2:#666; --accent:#4f46e5; --accent-l:#eef2ff; --danger:#dc2626; --danger-l:#fef2f2; --success:#059669; --success-l:#ecfdf5; --warn:#d97706; --warn-l:#fffbeb; --radius:10px; --mono:'SF Mono',Monaco,'Cascadia Code','Roboto Mono',monospace; }
*, *::before, *::after { box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; padding:0; background:var(--bg); color:var(--text); font-size:14px; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }

/* layout */
.app { display:flex; min-height:100vh; }
.sidebar { width:260px; background:var(--card); border-right:1px solid var(--border); padding:20px 0; flex-shrink:0; }
.sidebar h1 { font-size:17px; padding:0 20px 16px; margin:0; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:8px; }
.sidebar h1 .logo { width:28px; height:28px; background:var(--accent); border-radius:6px; display:flex; align-items:center; justify-content:center; color:#fff; font-size:14px; font-weight:700; }
.sidebar nav { padding:12px 0; }
.sidebar nav a { display:flex; align-items:center; gap:10px; padding:8px 20px; color:var(--text2); font-size:14px; font-weight:500; }
.sidebar nav a:hover { background:var(--accent-l); color:var(--accent); text-decoration:none; }
.sidebar nav a.active { background:var(--accent-l); color:var(--accent); border-right:3px solid var(--accent); }
.sidebar .stats { padding:16px 20px; border-top:1px solid var(--border); margin-top:auto; font-size:12px; color:var(--text2); }
.sidebar .stats div { margin-bottom:4px; }

.main { flex:1; padding:24px 32px; overflow-y:auto; }
.main h2 { margin:0 0 20px; font-size:20px; }

/* cards */
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:16px; }
.card { background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:18px; transition:box-shadow .15s; }
.card:hover { box-shadow:0 2px 12px rgba(0,0,0,.06); }
.card .card-header { display:flex; justify-content:space-between; align-items:start; margin-bottom:12px; }
.card .card-title { font-size:15px; font-weight:600; }
.card .card-meta { font-size:12px; color:var(--text2); margin-top:4px; }
.card .card-body { font-size:13px; color:var(--text2); margin-top:8px; }

/* badges */
.badge { display:inline-block; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.3px; }
.badge-draft { background:var(--warn-l); color:var(--warn); }
.badge-approved { background:var(--success-l); color:var(--success); }
.badge-rejected { background:var(--danger-l); color:var(--danger); }
.badge-invalid { background:#fef2f2; color:#991b1b; }
.badge-discovering { background:#eff6ff; color:#2563eb; }
.badge-discovered { background:var(--success-l); color:var(--success); }

/* buttons */
.btn { padding:6px 16px; border:none; border-radius:6px; font-size:13px; font-weight:500; cursor:pointer; transition:opacity .15s; }
.btn:hover { opacity:.85; }
.btn-approve { background:var(--success); color:#fff; }
.btn-reject { background:var(--danger); color:#fff; }
.btn-outline { background:transparent; border:1px solid var(--border); color:var(--text2); }
.btn-outline:hover { background:#f5f5f5; }
.btn-sm { padding:4px 12px; font-size:12px; }

/* table */
.table-wrap { background:var(--card); border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; }
table { width:100%; border-collapse:collapse; }
th, td { padding:10px 16px; text-align:left; border-bottom:1px solid #f0f0f0; font-size:13px; }
th { background:#fafafa; font-weight:600; font-size:12px; color:var(--text2); text-transform:uppercase; letter-spacing:.3px; }
tr:hover { background:#f8faff; }
tr:last-child td { border-bottom:none; }

/* yaml viewer */
.yaml-viewer { background:#1e1e2e; color:#cdd6f4; border-radius:var(--radius); padding:20px; font-family:var(--mono); font-size:13px; line-height:1.6; overflow-x:auto; white-space:pre-wrap; word-break:break-all; }

/* detail panel */
.detail-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
.detail-header h2 { margin:0; }
.detail-actions { display:flex; gap:8px; }

.detail-section { background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:20px; margin-bottom:16px; }
.detail-section h3 { margin:0 0 12px; font-size:15px; }
.detail-section dl { display:grid; grid-template-columns:auto 1fr; gap:8px 16px; margin:0; }
.detail-section dt { font-weight:600; color:var(--text2); font-size:13px; }
.detail-section dd { margin:0; font-size:13px; }

/* empty state */
.empty { text-align:center; padding:60px 20px; color:var(--text2); }
.empty .empty-icon { font-size:48px; margin-bottom:12px; }
.empty .empty-text { font-size:15px; }
.empty .empty-hint { font-size:13px; margin-top:8px; }

/* toast */
.toast { position:fixed; bottom:24px; right:24px; padding:12px 20px; border-radius:8px; color:#fff; font-size:14px; font-weight:500; z-index:999; opacity:0; transition:opacity .3s, transform .3s; transform:translateY(10px); }
.toast.show { opacity:1; transform:translateY(0); }
.toast.success { background:var(--success); }
.toast.error { background:var(--danger); }

/* candidate list */
.candidate-item { padding:12px; border:1px solid var(--border); border-radius:8px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:start; }
.candidate-item:hover { border-color:var(--accent); }
.candidate-info { flex:1; }
.candidate-info .url { font-family:var(--mono); font-size:12px; color:var(--accent); word-break:break-all; }
.candidate-info .desc { font-size:13px; color:var(--text2); margin-top:4px; }
.candidate-score { font-size:12px; font-weight:600; color:var(--success); white-space:nowrap; margin-left:12px; }

/* filter bar */
.filter-bar { display:flex; gap:8px; margin-bottom:20px; align-items:center; }
.filter-bar select, .filter-bar input { padding:6px 12px; border:1px solid var(--border); border-radius:6px; font-size:13px; background:var(--card); }
.filter-bar .spacer { flex:1; }
</style>
</head>
<body>
<div class="app">
  <div class="sidebar">
    <h1><span class="logo">H</span> fd-scraw-harness</h1>
    <nav>
      <a href="#" class="nav-link active" data-view="manifests">📋 Manifests</a>
      <a href="#" class="nav-link" data-view="discoveries">🔍 Discoveries</a>
    </nav>
    <div class="stats" id="stats">Loading...</div>
  </div>
  <div class="main" id="content">
    <!-- dynamic content -->
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
const API = '';
let currentView = 'manifests';
let currentFilter = '';
let manifestCache = {};

// --- helpers ---
async function api(path, method='GET') {
  const res = await fetch(API + path, { method });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function getManifest(id) {
  if (!manifestCache[id]) {
    manifestCache[id] = await api(`/api/manifests/${id}`);
  }
  return manifestCache[id];
}
function esc(s) { const d=document.createElement('div'); d.textContent=s??''; return d.innerHTML; }
function fmtDate(s) { if(!s) return '-'; return s.replace('T',' ').slice(0,16); }
function badge(status) {
  const cls = {'draft':'badge-draft','approved':'badge-approved','rejected':'badge-rejected','invalid':'badge-invalid','discovering':'badge-discovering','discovered':'badge-discovered'}[status]||'badge-draft';
  return `<span class="badge ${cls}">${esc(status)}</span>`;
}
function toast(msg, type='success') {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = `toast show ${type}`;
  setTimeout(() => t.classList.remove('show'), 2500);
}

// --- views ---
async function loadStats() {
  const ms = await api('/api/manifests');
  const ds = await api('/api/discoveries');
  const draft = ms.filter(m=>m.status==='draft').length;
  const approved = ms.filter(m=>m.status==='approved').length;
  document.getElementById('stats').innerHTML = `
    <div>📊 Manifests: ${ms.length} (${draft} draft, ${approved} approved)</div>
    <div>🔍 Discoveries: ${ds.length}</div>
  `;
}

async function showManifests() {
  const ms = await api('/api/manifests');
  const filtered = currentFilter ? ms.filter(m=>m.status===currentFilter) : ms;

  if (!filtered.length) {
      <h2>Manifests</h2>
      <div class="empty">
        <div class="empty-icon">📋</div>
        <div class="empty-text">No manifests yet</div>
        <div class="empty-hint">Run <code>fd-scraw-harness discover "topic"</code> to get started</div>
      </div>`;
    return;
  }

  const cards = filtered.map(m => `
    <div class="card" onclick="showManifestDetail(${m.id})" style="cursor:pointer" role="button" tabindex="0" onkeypress="if(event.key==='Enter')showManifestDetail(${m.id})">
      <div class="card-header">
        <div>
          <div class="card-title">${esc(m.source_name || 'Untitled')} #${m.id}</div>
          <div class="card-meta">Discovery #${m.discovery_id} · ${fmtDate(m.created_at)}</div>
        </div>
        ${badge(m.status)}
      </div>
      <div class="card-body">
        <div>Model: ${esc(m.model_used || '-')}</div>
        ${m.validation_error ? `<div style="color:var(--danger);margin-top:4px;">⚠ ${esc(m.validation_error.slice(0,100))}</div>` : ''}
      </div>
    </div>`).join('');

    <div class="detail-header">
      <h2>Manifests</h2>
    </div>
    <div class="filter-bar">
      <select id="filter-select" onchange="applyFilter(this.value)">
        <option value="">All statuses</option>
        <option value="draft" ${currentFilter==='draft'?'selected':''}>Draft</option>
        <option value="approved" ${currentFilter==='approved'?'selected':''}>Approved</option>
        <option value="rejected" ${currentFilter==='rejected'?'selected':''}>Rejected</option>
        <option value="invalid" ${currentFilter==='invalid'?'selected':''}>Invalid</option>
      </select>
      <div class="spacer"></div>
      <span style="font-size:13px;color:var(--text2)">${filtered.length} manifest(s)</span>
    </div>
    <div class="grid" id="manifest-grid">${cards}</div>`;
  
  // Attach event listeners to all cards
  document.querySelectorAll('#manifest-grid .card').forEach(card => {
    card.addEventListener('click', () => {});
  });
}

async function applyFilter(filter) {
  currentFilter = filter;
  await showManifests();
}

// Make functions globally accessible
window.approveManifest = approveManifest;
window.rejectManifest = rejectManifest;

// Restore saved filter when loading manifests view
(function() {
  const saved = localStorage.getItem('harness-filter');
  if (saved) currentFilter = saved;
})();

async function showManifestDetail(id) {
  const m = await getManifest(id);
  const d = m.discovery ? await api(`/api/discoveries/${m.discovery_id}`) : null;

  const actions = m.status === 'draft'
    ? `<button class="btn btn-approve btn-sm" onclick="window.approveManifest(${id})">✓ Approve</button>
       <button class="btn btn-reject btn-sm" onclick="window.rejectManifest(${id})">✕ Reject</button>`
    : m.status === 'approved'
    ? `<button class="btn btn-outline btn-sm" onclick="window.rejectManifest(${id})">Revoke</button>`
    : `<button class="btn btn-approve btn-sm" onclick="window.approveManifest(${id})">✓ Approve</button>`;

    <div class="detail-header">
      <div>
        <h2>${esc(m.source_name || 'Untitled')} <span style="font-size:14px;color:var(--text2)">#${m.id}</span></h2>
        ${badge(m.status)}
      </div>
      <div class="detail-actions">${actionsHtml || '(no actions)'}</div>
    </div>
    <div class="detail-section">
      <h3>Info</h3>
      <dl>
        <dt>ID</dt><dd>${m.id}</dd>
        <dt>Discovery</dt><dd><a href="#" onclick="showDiscoveryDetail(${m.discovery_id});return false">#${m.discovery_id}</a></dd>
        <dt>Model</dt><dd>${esc(m.model_used || '-')}</dd>
        <dt>Created</dt><dd>${fmtDate(m.created_at)}</dd>
        <dt>Updated</dt><dd>${fmtDate(m.updated_at)}</dd>
        ${m.validation_error ? `<dt>Error</dt><dd style="color:var(--danger)">${esc(m.validation_error)}</dd>` : ''}
      </dl>
    </div>
    <div class="detail-section">
      <h3>Manifest YAML</h3>
      <div class="yaml-viewer">${esc(m.manifest_yaml)}</div>
    </div>`;
}

// Restore saved filter on view switch
  if (currentView === 'manifests') {
    currentFilter = localStorage.getItem('harness-filter') || '';
  }

function onFilterChange(value) {
  currentFilter = value;
  localStorage.setItem('harness-filter', value);
  showManifests();
}

// Ensure we're in the right scope
if (typeof showManifestDetail !== 'function') {
  console.error("Functions not loaded yet");
}

async function showDiscoveries() {
  console.log("showDiscoveries called");
  const ds = await api('/api/discoveries');
  if (!ds.length) {
      <h2>Discoveries</h2>
      <div class="empty">
        <div class="empty-icon">🔍</div>
        <div class="empty-text">No discoveries yet</div>
        <div class="empty-hint">Run <code>fd-scraw-harness discover "topic"</code> to get started</div>
      </div>`;
    return;
  }

  const cards = ds.map(d => `
    <div class="card" onclick="window.showDiscoveryDetail(${d.id})" style="cursor:pointer; transition:box-shadow .15s;border:2px solid transparent;" onmouseover="this.style.boxShadow='0 4px 16px rgba(79,70,229,0.1)' " onmouseout="this.style.boxShadow='' ">
      <div class="card-header">
        <div>
          <div class="card-title">${esc(d.query)}</div>
          <div class="card-meta">#${d.id} · ${d.query_type} · ${fmtDate(d.created_at)}</div>
        </div>
        ${badge(d.status)}
      </div>
      <div class="card-body">${d.candidate_count || 0} candidate(s)</div>
    </div>`).join('');

    <h2>Discoveries</h2>
    <div class="grid">${cards}</div>`;
}

// Clear cache when viewing discovery details
manifestCache = {};

async function showDiscoveryDetail(id) {
  console.log("Viewing discovery", id);
  const d = await api(`/api/discoveries/${id}`);
  const cands = (d.candidates || []).map((c, i) => `
    <div class="candidate-item">
      <div class="candidate-info">
        <div class="url">${esc(c.url)}</div>
        ${c.title ? `<div style="font-weight:600;margin-top:4px">${esc(c.title)}</div>` : ''}
        ${c.description ? `<div class="desc">${esc(c.description)}</div>` : ''}
        ${c.estimated_data_type ? `<div class="desc">Type: ${esc(c.estimated_data_type)}</div>` : ''}
      </div>
      <div class="candidate-score">${c.score || 0}</div>
    </div>`).join('');

    <div class="detail-header">
      <div>
        <h2>${esc(d.query)} <span style="font-size:14px;color:var(--text2)">#${d.id}</span></h2>
        ${badge(d.status)}
      </div>
      <div class="detail-actions">
        <button class="btn btn-outline btn-sm" onclick="currentView='manifests';navTo('manifests')">← Back to Manifests</button>
      </div>
    </div>
    <div class="detail-section">
      <h3>Info</h3>
      <dl>
        <dt>ID</dt><dd>${d.id}</dd>
        <dt>Query</dt><dd>${esc(d.query)}</dd>
        <dt>Type</dt><dd>${esc(d.query_type)}</dd>
        <dt>Status</dt><dd>${badge(d.status)}</dd>
        <dt>Created</dt><dd>${fmtDate(d.created_at)}</dd>
      </dl>
    </div>
    <div class="detail-section">
      <h3>Candidates (${(d.candidates||[]).length})</h3>
      ${cands || '<div style="color:var(--text2)">No candidates</div>'}
    </div>`;
}

// --- actions ---
async function approveManifest(id) {
  try {
    await api(`/api/manifests/${id}/approve`, 'POST');
    toast('Manifest approved');
    await showManifestDetail(id);
    loadStats();
  } catch(e) { toast(e.message, 'error'); }
}
async function rejectManifest(id) {
  try {
    await api(`/api/manifests/${id}/reject`, 'POST');
    toast('Manifest rejected');
    await showManifestDetail(id);
    loadStats();
  } catch(e) { toast(e.message, 'error'); }
}

// --- nav ---
function navTo(view) {
  currentView = view;
  document.querySelectorAll('.nav-link').forEach(a => a.classList.toggle('active', a.dataset.view === view));
  if (view === 'manifests') showManifests();
  if (view === 'discoveries') showDiscoveries();
}
document.querySelectorAll('.nav-link').forEach(a => {
  a.addEventListener('click', e => { e.preventDefault(); navTo(a.dataset.view); });
});

// init
showManifests();
loadStats();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self):
        body = HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            return self._send_html()

        if path == "/api/manifests":
            with get_session() as sess:
                ms = sess.query(Manifest).order_by(Manifest.created_at.desc()).all()
                return self._send_json([{
                    "id": m.id,
                    "discovery_id": m.discovery_id,
                    "source_name": m.source_name,
                    "model_used": m.model_used,
                    "status": m.status,
                    "validation_error": m.validation_error,
                    "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else None,
                } for m in ms])

        if path.startswith("/api/manifests/"):
            parts = path.split("/")
            if len(parts) == 3:
                try:
                    mid = int(parts[2])
                except ValueError:
                    return self._send_json({"error": "invalid id"}, 400)
                with get_session() as sess:
                    m = sess.query(Manifest).filter_by(id=mid).first()
                    if not m:
                        return self._send_json({"error": "not found"}, 404)
                    return self._send_json({
                        "id": m.id,
                        "discovery_id": m.discovery_id,
                        "source_name": m.source_name,
                        "model_used": m.model_used,
                        "status": m.status,
                        "validation_error": m.validation_error,
                        "manifest_yaml": m.manifest_yaml,
                        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else None,
                        "updated_at": m.updated_at.strftime("%Y-%m-%d %H:%M") if m.updated_at else None,
                    })


        # Single discovery detail endpoint
        if path.startswith("/api/discoveries/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 2 and parts[1] == "discoveries":
                try:
                    did = int(parts[2])
                except (ValueError, IndexError):
                    return self._send_json({"error": "invalid id"}, 400)
                
                with get_session() as sess:
                    d = sess.query(Discovery).filter_by(id=did).first()
                    if not d:
                        return self._send_json({"error": "not found"}, 404)
                    
                    cands = sess.query(Candidate).filter_by(discovery_id=did).all()
                    return self._send_json({
                        "id": d.id,
                        "query": d.query,
                        "query_type": d.query_type,
                        "status": d.status,
                        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else None,
                        "candidates": [{
                            "id": c.id,
                            "url": c.url,
                            "title": c.title,
                            "description": c.description,
                            "estimated_data_type": c.estimated_data_type,
                            "score": c.score,
                        } for c in cands],
                    })
        if path == "/api/discoveries":
            with get_session() as sess:
                ds = sess.query(Discovery).order_by(Discovery.created_at.desc()).all()
                result = []
                for d in ds:
                    cand_count = sess.query(Candidate).filter_by(discovery_id=d.id).count()
                    result.append({
                        "id": d.id,
                        "query": d.query,
                        "query_type": d.query_type,
                        "status": d.status,
                        "candidate_count": cand_count,
                        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else None,
                    })
                return self._send_json(result)

        if path.startswith("/api/discoveries/"):
            parts = path.split("/")
            if len(parts) == 3:
                try:
                    did = int(parts[2])
                except ValueError:
                    return self._send_json({"error": "invalid id"}, 400)
                with get_session() as sess:
                    d = sess.query(Discovery).filter_by(id=did).first()
                    if not d:
                        return self._send_json({"error": "not found"}, 404)
                    cands = sess.query(Candidate).filter_by(discovery_id=did).all()
                    return self._send_json({
                        "id": d.id,
                        "query": d.query,
                        "query_type": d.query_type,
                        "status": d.status,
                        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else None,
                        "candidates": [{
                            "id": c.id,
                            "url": c.url,
                            "title": c.title,
                            "description": c.description,
                            "estimated_data_type": c.estimated_data_type,
                            "score": c.score,
                        } for c in cands],
                    })

        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path.endswith("/approve"):
            mid = int(path.split("/")[3])
            with get_session() as sess:
                m = sess.query(Manifest).filter_by(id=mid).first()
                if not m:
                    return self._send_json({"error": "not found"}, 404)
                m.status = "approved"
                sess.commit()
                return self._send_json({"ok": True, "status": "approved"})

        if path.endswith("/reject"):
            mid = int(path.split("/")[3])
            with get_session() as sess:
                m = sess.query(Manifest).filter_by(id=mid).first()
                if not m:
                    return self._send_json({"error": "not found"}, 404)
                m.status = "rejected"
                sess.commit()
                return self._send_json({"ok": True, "status": "rejected"})

        self._send_json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8892
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"fd-scraw-harness dashboard → http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
