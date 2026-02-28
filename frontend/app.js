// Local Pseudonymization Tool — Frontend v4.0.0

const API = '';
const LS_MODE = 'pst_mode';
const LS_LDAP = 'pst_ldap_config';
const LS_SESSIONS = 'pst_sessions';
const LS_PRESET = 'pst_preset';
const LS_SOURCE_MODE = 'pst_source_mode';

const state = {
  mode: localStorage.getItem(LS_MODE) || 'light',
  preset: localStorage.getItem(LS_PRESET) || 'SOC Logs',
  sourceMode: localStorage.getItem(LS_SOURCE_MODE) || 'console',
  batches: {},
  activeBatchId: null,
  currentPassphrase: null,
  passphraseVisible: false,
};

// ─── INIT ────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  setMode(state.mode, false);
  setSourceMode(state.sourceMode, false);
  setPreset(state.preset, false);
  checkServerHealth();
  setInterval(checkServerHealth, 15000);
  loadDictStatus();
  refreshPolicyPreview();
  restoreLdapConfig();
  restoreSessionHistory();

  const ta = document.getElementById('composer-textarea');
  ta.addEventListener('input', () => {
    document.getElementById('composer-char-count').textContent =
      ta.value.length.toLocaleString('it') + ' caratteri';
  });
  ta.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); scanComposer(); }
  });

  // Drag-and-drop drop zone
  const dropZone = document.getElementById('composer-section') || document.body;
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drop-zone-active');
  });
  dropZone.addEventListener('dragleave', (e) => {
    if (!dropZone.contains(e.relatedTarget)) dropZone.classList.remove('drop-zone-active');
  });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drop-zone-active');
    const files = Array.from(e.dataTransfer.files);
    if (files.length) handleFileUploadDirect(files);
  });
});

// ─── HEALTH ──────────────────────────────────────────────────────────────────

async function checkServerHealth() {
  const dot = document.getElementById('server-status');
  try {
    const ready = await fetch(API + '/api/ready', { signal: AbortSignal.timeout(3000) });
    const r = ready.ok ? ready : await fetch(API + '/api/health', { signal: AbortSignal.timeout(3000) });
    if (r.ok) {
      dot.className = 'status-dot status-ok';
      dot.title = 'Server attivo';
    } else {
      dot.className = 'status-dot status-error';
      dot.title = 'Server non raggiungibile';
    }
  } catch {
    dot.className = 'status-dot status-error';
    dot.title = 'Server non raggiungibile';
  }
}

// ─── MODE ────────────────────────────────────────────────────────────────────

function setMode(m, save) {
  if (save === undefined) save = true;
  state.mode = m;
  if (save) localStorage.setItem(LS_MODE, m);
  document.getElementById('mode-light').classList.toggle('active', m === 'light');
  document.getElementById('mode-strict').classList.toggle('active', m === 'strict');
  const el = document.getElementById('info-mode');
  if (el) el.textContent = m === 'light' ? 'Light' : 'Strict';
}

function setSourceMode(mode, save) {
  if (save === undefined) save = true;
  state.sourceMode = mode;
  if (save) localStorage.setItem(LS_SOURCE_MODE, mode);
  const btnConsole = document.getElementById('source-console');
  const btnFile = document.getElementById('source-file');
  if (btnConsole) btnConsole.classList.toggle('active', mode === 'console');
  if (btnFile) btnFile.classList.toggle('active', mode === 'file');
}

function setPreset(preset, save) {
  if (save === undefined) save = true;
  state.preset = preset;
  if (save) localStorage.setItem(LS_PRESET, preset);
  const select = document.getElementById('preset-select');
  if (select) select.value = preset;
  refreshPolicyPreview();
}

async function refreshPolicyPreview() {
  const box = document.getElementById('policy-preview');
  if (!box) return;
  try {
    const encoded = encodeURIComponent(state.preset);
    const r = await fetch(API + '/api/settings/policies/' + encoded);
    if (!r.ok) throw new Error('Policy non disponibile');
    const d = await r.json();
    const sample = (d.enabled_entity_types || []).slice(0, 8).join(', ');
    box.textContent = 'Policy: ' + d.preset + ' · Soglia ' + d.confidence_threshold + ' · Entità abilitate: ' + d.entity_count + (sample ? ' (' + sample + (d.entity_count > 8 ? ', ...' : '') + ')' : '');
  } catch {
    box.textContent = 'Policy attiva: ' + state.preset;
  }
}

// ─── CLIPBOARD ───────────────────────────────────────────────────────────────

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    const ta = document.getElementById('composer-textarea');
    ta.value = text;
    ta.dispatchEvent(new Event('input'));
    toast('Testo incollato dagli appunti', 'success');
  } catch {
    toast('Incolla manualmente con Ctrl+V.', 'warning');
  }
}

// ─── FLUSSO 1: TESTO INLINE ──────────────────────────────────────────────────

async function scanComposer() {
  if (state.sourceMode !== 'console') {
    toast('Modalità corrente: File. Passa a Console per scansionare testo inline.', 'warning');
    return;
  }
  const ta = document.getElementById('composer-textarea');
  const text = ta.value.trim();
  if (!text) { toast('Inserisci del testo prima di scansionare.', 'warning'); return; }
  const btn = document.getElementById('scan-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Scansione...';
  const cardEl = createBatchCard(null, 'Testo inline', 'scanning');
  try {
    const r = await fetch(API + '/api/console/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, mode: state.mode, preset: state.preset }),
    });
    if (!r.ok) {
      let msg = 'Errore ' + r.status;
      try { const e = await r.json(); msg = e.detail || JSON.stringify(e); } catch {}
      throw new Error(msg);
    }
    const data = await r.json();
    const batchId = data.batch_id;
    cardEl.dataset.batchId = batchId;
    state.batches[batchId] = {
      id: batchId,
      label: 'Testo inline',
      mode: state.mode,
      status: 'review',
      findings: data.findings || [],
      inputText: text,
      fileId: data.file_id,
      passphrase: data.passphrase,
      createdAt: new Date().toISOString(),
    };
    state.activeBatchId = batchId;
    state.currentPassphrase = data.passphrase;
    updateCardReady(cardEl, batchId, data);
    addToSidebar(batchId, 'Testo inline', (data.findings || []).length);
    saveSessionHistory(batchId, 'Testo inline', (data.findings || []).length);
    showPassphraseModal(data.passphrase);
  } catch (err) {
    updateCardError(cardEl, err.message);
    toast('Errore scansione: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 Scansiona';
  }
}

// ─── FLUSSO 2: UPLOAD FILE ───────────────────────────────────────────────────

async function handleFileUpload(event) {
  if (state.sourceMode !== 'file') {
    toast('Modalità corrente: Console. Passa a File per caricare documenti.', 'warning');
    return;
  }
  const files = Array.from(event.target.files);
  if (!files.length) return;
  event.target.value = '';
  for (const file of files) {
    const cardEl = createBatchCard(null, file.name, 'uploading');
    try {
      const fd = new FormData();
      fd.append('files', file);
      fd.append('mode', state.mode);
      fd.append('preset', state.preset);
      // NON impostare Content-Type: il browser lo imposta con il boundary corretto
      const r = await fetch(API + '/api/batches', { method: 'POST', body: fd });
      if (!r.ok) {
        let msg = 'Errore ' + r.status;
        try { const e = await r.json(); msg = e.detail || JSON.stringify(e); } catch {}
        throw new Error(msg);
      }
      const data = await r.json();
      const batchId = data.batch_id;
      cardEl.dataset.batchId = batchId;
      state.batches[batchId] = {
        id: batchId,
        label: file.name,
        mode: state.mode,
        status: 'review',
        findings: data.findings || [],
        inputText: null,
        fileId: data.files && data.files.length > 0 ? data.files[0].id : null,
        passphrase: data.passphrase,
        createdAt: new Date().toISOString(),
      };
      state.activeBatchId = batchId;
      state.currentPassphrase = data.passphrase;
      updateCardReady(cardEl, batchId, data);
      addToSidebar(batchId, file.name, (data.findings || []).length);
      saveSessionHistory(batchId, file.name, (data.findings || []).length);
      showPassphraseModal(data.passphrase);
    } catch (err) {
      updateCardError(cardEl, err.message);
      toast('Errore upload ' + file.name + ': ' + err.message, 'error');
    }
  }
}

// ─── REVIEW DECISIONS ────────────────────────────────────────────────────────

async function submitReviewDecisions(batchId) {
  const batch = state.batches[batchId];
  if (!batch || !batch.findings || !batch.findings.length) return true;
  // Legge il valore aggiornato degli input direttamente dal DOM (evita race condition con oninput)
  const domInputs = {};
  document.querySelectorAll('#drawer-review-body .finding-pseudonym-input').forEach(inp => {
    if (inp.dataset.fid) domInputs[inp.dataset.fid] = inp.value;
  });
  const decisions = batch.findings.map(f => {
    const domVal = domInputs[f.finding_id];
    const pseudonym = domVal !== undefined ? domVal : (f.proposed_pseudonym || null);
    const action = f._action || 'accept';
    return {
      finding_id: f.finding_id,
      action: action.toLowerCase(),
      modified_pseudonym: (action === 'modify' || f._modified) ? pseudonym : null,
    };
  });
  const r = await fetch(API + '/api/batches/' + batchId + '/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decisions: decisions }),
  });
  if (!r.ok) {
    let m = 'Errore invio review ' + r.status;
    try { const e = await r.json(); m = e.detail || m; } catch {}
    throw new Error(m);
  }
  return true;
}

// ─── APPLY ───────────────────────────────────────────────────────────────────

async function applyCurrentBatch() {
  const batchId = state.activeBatchId;
  if (!batchId) { toast('Nessun batch attivo.', 'warning'); return; }
  const batch = state.batches[batchId];
  if (!batch) { toast('Batch non trovato.', 'error'); return; }
  const btn = document.getElementById('apply-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Applicazione...'; }
  try {
    // Invia sempre le decisions prima di apply
    if (batch.findings && batch.findings.length > 0) {
      await submitReviewDecisions(batchId);
    }
    if (batch.inputText !== undefined && batch.inputText !== null) {
      // Flusso testo inline
      const r = await fetch(API + '/api/console/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ batch_id: batchId, file_id: batch.fileId, text: batch.inputText }),
      });
      if (!r.ok) {
        let m = 'Errore ' + r.status;
        try { const e = await r.json(); m = e.detail || m; } catch {}
        throw new Error(m);
      }
      const data = await r.json();
      batch.status = 'done';
      updateSidebarItemDone(batchId);
      closeDrawer();
      showTextResult(batchId, data);
      toast('Pseudonimizzazione completata.', 'success');
    } else {
      // Flusso file
      const r = await fetch(API + '/api/batches/' + batchId + '/apply', { method: 'POST' });
      if (!r.ok) {
        let m = 'Errore ' + r.status;
        try { const e = await r.json(); m = e.detail || m; } catch {}
        throw new Error(m);
      }
      batch.status = 'done';
      updateSidebarItemDone(batchId);
      closeDrawer();
      toast('Completato. Download in corso...', 'success');
      const dl = await fetch(API + '/api/batches/' + batchId + '/download');
      if (!dl.ok) throw new Error('Download fallito: ' + dl.status);
      const blob = await dl.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'batch_' + batchId.slice(0, 8) + '.zip';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  } catch (err) {
    toast('Errore apply: ' + err.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '✓ Applica Pseudonimizzazione'; }
  }
}

async function quickApply(batchId) {
  state.activeBatchId = batchId;
  await applyCurrentBatch();
}

// ─── RISULTATO TESTO ─────────────────────────────────────────────────────────

function showTextResult(batchId, data) {
  const cardEl = document.querySelector('[data-batch-id="' + batchId + '"]');
  if (!cardEl) return;
  let out = cardEl.querySelector('.card-output');
  if (!out) { out = document.createElement('div'); cardEl.appendChild(out); }
  out.className = 'card-output';
  const warnings = data.residual_warnings || [];
  const appliedCount = data.applied_count || 0;
  const safety = data.safety_label || 'SAFE_TO_UPLOAD';
  out.innerHTML =
    '<div class="output-header">' +
      '<span class="output-label">Testo pseudonimizzato (' + appliedCount + ' sostituzioni)</span>' +
      '<button class="btn btn-sm btn-ghost" onclick="copyOutput(\'' + batchId + '\')">&#x1F4CB; Copia</button>' +
    '</div>' +
    '<div class="output-clean"><b>Safety:</b> ' + escHtml(safety) + '</div>' +
    '<pre class="output-text" id="output-text-' + batchId + '">' + escHtml(data.pseudonymized_text || '') + '</pre>' +
    (warnings.length
      ? '<div class="output-warnings"><b>&#x26A0; Possibili residui (' + warnings.length + '):</b><ul>' +
        warnings.map(w => '<li>' + escHtml(w) + '</li>').join('') + '</ul></div>'
      : '<div class="output-clean">&#x2713; Nessun residuo rilevato</div>');
}

async function copyOutput(batchId) {
  const el = document.getElementById('output-text-' + batchId);
  if (!el) return;
  try {
    await navigator.clipboard.writeText(el.textContent);
    toast('Testo copiato.', 'success');
  } catch {
    toast('Impossibile copiare. Seleziona manualmente.', 'warning');
  }
}

// ─── CARD DOM ────────────────────────────────────────────────────────────────

function createBatchCard(batchId, label, status) {
  const container = document.getElementById('cards-container');
  const empty = document.getElementById('sidebar-empty');
  if (empty) empty.style.display = 'none';
  const card = document.createElement('div');
  card.className = 'batch-card batch-card-' + status;
  if (batchId) card.dataset.batchId = batchId;
  card._label = label;
  card.innerHTML =
    '<div class="card-header">' +
      '<span class="card-label">' + escHtml(label) + '</span>' +
      '<span class="card-status-badge badge-' + status + '">' + statusLabel(status) + '</span>' +
    '</div>' +
    '<div class="card-body"><div class="card-spinner">&#x23F3; Elaborazione in corso...</div></div>';
  container.insertBefore(card, container.firstChild);
  return card;
}

function updateCardReady(cardEl, batchId, data) {
  const findings = data.findings || [];
  const safety = data.safety_label || 'SAFE_TO_UPLOAD';
  const safetyClass = safety === 'NOT_SAFE' ? 'safety-blocked' : safety === 'SAFE_WITH_WARNINGS' ? 'safety-review' : 'safety-ok';
  const byType = {};
  findings.forEach(f => { byType[f.entity_type] = (byType[f.entity_type] || 0) + 1; });
  const chips = Object.entries(byType)
    .sort((a, b) => b[1] - a[1])
    .map(([t, n]) => '<span class="type-chip">' + escHtml(t) + ' <b>' + n + '</b></span>')
    .join('');
  const label = (state.batches[batchId] && state.batches[batchId].label) || cardEl._label || batchId.slice(0, 8);
  cardEl.className = 'batch-card batch-card-review';
  cardEl.dataset.batchId = batchId;
  cardEl.innerHTML =
    '<div class="card-header">' +
      '<span class="card-label">' + escHtml(label) + '</span>' +
      '<span class="safety-label ' + safetyClass + '">' + safety.replace(/_/g, ' ') + '</span>' +
    '</div>' +
    '<div class="card-body">' +
      '<div class="card-stats">' +
        '<span class="stat-main">' + findings.length + ' finding</span>' +
        '<div class="type-chips">' +
          (chips || '<span class="no-findings">Nessun dato sensibile rilevato</span>') +
        '</div>' +
      '</div>' +
      '<div class="card-actions">' +
        '<button class="btn btn-secondary" onclick="openReview(\'' + batchId + '\')">&#x1F50E; Rivedi</button>' +
        '<button class="btn btn-primary" onclick="quickApply(\'' + batchId + '\')">&#x2713; Applica</button>' +
      '</div>' +
    '</div>';
}

function updateCardError(cardEl, msg) {
  cardEl.className = 'batch-card batch-card-error';
  cardEl.innerHTML =
    '<div class="card-header"><span class="card-label">Errore</span>' +
    '<span class="card-status-badge badge-error">&#x2717; Errore</span></div>' +
    '<div class="card-body"><div class="card-error-msg">&#x26A0; ' + escHtml(msg) + '</div></div>';
}

function statusLabel(s) {
  const map = {
    scanning: '⏳ Scansione',
    uploading: '⏳ Upload',
    review: '🔍 Review',
    done: '✓ Fatto',
    error: '✗ Errore',
  };
  return map[s] || s;
}

// ─── SIDEBAR ─────────────────────────────────────────────────────────────────

function addToSidebar(batchId, label, count) {
  const list = document.getElementById('sidebar-list');
  const empty = document.getElementById('sidebar-empty');
  if (empty) empty.style.display = 'none';
  const item = document.createElement('div');
  item.className = 'sidebar-item';
  item.id = 'sidebar-' + batchId;
  item.onclick = () => { state.activeBatchId = batchId; openReview(batchId); };
  const now = new Date();
  const timeStr = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');
  item.innerHTML =
    '<div class="sidebar-item-main">' +
      '<span class="sidebar-item-label" title="' + escHtml(label) + '">' + escHtml(label) + '</span>' +
      '<span class="sidebar-item-count" id="sidebar-count-' + batchId + '">' + count + '</span>' +
    '</div>' +
    '<div class="sidebar-item-meta">' +
      '<span class="sidebar-item-time">' + timeStr + '</span>' +
    '</div>';
  list.insertBefore(item, list.firstChild);
}

function updateSidebarItemDone(batchId) {
  const el = document.getElementById('sidebar-' + batchId);
  if (el) el.classList.add('sidebar-item-done');
}

async function clearAllBatches() {
  for (const batchId of Object.keys(state.batches)) {
    try { await fetch(API + '/api/batches/' + batchId, { method: 'DELETE' }); } catch {}
  }
  state.batches = {};
  state.activeBatchId = null;
  document.getElementById('cards-container').innerHTML = '';
  document.getElementById('sidebar-list').innerHTML =
    '<div class="sidebar-empty" id="sidebar-empty">Nessuna sessione attiva</div>';
  clearSessionHistory();
}

// ─── SESSION HISTORY (localStorage) ─────────────────────────────────────────

function saveSessionHistory(batchId, label, count) {
  try {
    const sessions = JSON.parse(localStorage.getItem(LS_SESSIONS) || '[]');
    sessions.unshift({
      id: batchId,
      label: label,
      count: count,
      ts: new Date().toISOString(),
    });
    // Mantieni solo le ultime 20 sessioni
    localStorage.setItem(LS_SESSIONS, JSON.stringify(sessions.slice(0, 20)));
  } catch {}
}

function restoreSessionHistory() {
  try {
    const sessions = JSON.parse(localStorage.getItem(LS_SESSIONS) || '[]');
    if (!sessions.length) return;
    const histEl = document.getElementById('session-history');
    if (!histEl) return;
    histEl.innerHTML = '';
    sessions.forEach(s => {
      const d = document.createElement('div');
      d.className = 'history-item';
      const ts = new Date(s.ts);
      const dateStr = ts.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }) +
        ' ' + ts.getHours().toString().padStart(2, '0') + ':' + ts.getMinutes().toString().padStart(2, '0');
      d.innerHTML =
        '<span class="history-label" title="' + escHtml(s.label) + '">' + escHtml(s.label) + '</span>' +
        '<span class="history-meta">' + s.count + ' finding &middot; ' + dateStr + '</span>';
      histEl.appendChild(d);
    });
    const section = document.getElementById('session-history-section');
    if (section) section.style.display = 'block';
  } catch {}
}

function clearSessionHistory() {
  localStorage.removeItem(LS_SESSIONS);
  const histEl = document.getElementById('session-history');
  if (histEl) histEl.innerHTML = '';
  const section = document.getElementById('session-history-section');
  if (section) section.style.display = 'none';
}

// ─── REVIEW DRAWER ───────────────────────────────────────────────────────────

function openReview(batchId) {
  state.activeBatchId = batchId;
  const batch = state.batches[batchId];
  if (!batch) return;
  const findings = batch.findings || [];
  const typeFilter = document.getElementById('review-type-filter');
  const types = [...new Set(findings.map(f => f.entity_type))].sort();
  typeFilter.innerHTML = '<option value="">Tutti i tipi</option>' +
    types.map(t => '<option value="' + escHtml(t) + '">' + escHtml(t) + '</option>').join('');
  findings.forEach(f => { if (!f._action) f._action = 'accept'; });
  renderFindings(findings);
  document.getElementById('review-count').textContent = findings.length + ' finding';
  openDrawer('review');
}

function renderFindings(findings) {
  var body = document.getElementById('drawer-review-body');
  if (!findings.length) {
    body.innerHTML = '<div class="no-findings-msg">Nessun finding.</div>';
    return;
  }
  var rows = [];
  for (var i = 0; i < findings.length; i++) {
    var f = findings[i];
    var action = f._action || 'accept';
    // Classi riga
    var rowClass = 'finding-row';
    if (action === 'reject') rowClass += ' finding-rejected';
    else if (action === 'accept') rowClass += ' finding-accepted';
    if (f._modified) rowClass += ' finding-modified';

    var fid = escHtml(f.finding_id);

    // Colonna 1: badge tipo + confidence
    var conf = f.confidence_score != null ? Math.round(f.confidence_score * 100) : null;
    var confClass = conf != null ? (conf >= 90 ? 'conf-high' : conf >= 60 ? 'conf-mid' : 'conf-low') : '';
    var confBadge = conf != null ? '<span class="finding-conf ' + confClass + '">' + conf + '%</span>' : '';
    var entityClass = 'entity-badge entity-' + escHtml(f.entity_type);
    var col1 = '<div class="finding-badge-cell"><span class="' + entityClass + '">' + escHtml(f.entity_type) + '</span>' + confBadge + '</div>';

    // Colonna 2: valore originale (tooltip completo)
    var col2 = '<span class="finding-original" title="' + escHtml(f.original_value) + '">' + escHtml(f.original_value) + '</span>';

    // Colonna 3: input pseudonimo — usa oninput per aggiornare in tempo reale
    var col3 = '<input class="finding-pseudonym-input" type="text" value="' + escHtml(f.proposed_pseudonym || '') +
      '" data-fid="' + fid + '" oninput="updatePseudonym(this.dataset.fid, this.value)" />';

    // Colonna 4: toggle accept/reject
    var taClass = 'finding-toggle-accept' + (action === 'accept' ? ' active' : '');
    var trClass = 'finding-toggle-reject' + (action === 'reject' ? ' active' : '');
    var col4 = '<div class="finding-toggle-group">' +
      '<button class="' + taClass + '" data-fid="' + fid + '" data-act="accept" ' +
        'onclick="setFindingAction(this.dataset.fid, this.dataset.act)" title="Accetta">&#x2713; Acc</button>' +
      '<button class="' + trClass + '" data-fid="' + fid + '" data-act="reject" ' +
        'onclick="setFindingAction(this.dataset.fid, this.dataset.act)" title="Rifiuta">&#x2717; Rig</button>' +
      '</div>';

    // Colonna 5: rimuovi dal batch
    var col5 = '<button class="finding-remove-btn" data-fid="' + fid + '" ' +
      'onclick="removeFinding(this.dataset.fid)" title="Rimuovi">&#x2715;</button>';

    // Snippet di contesto (span su tutta la griglia, visibile all'hover via CSS)
    var snippet = f.context_snippet
      ? '<span class="finding-snippet-row">' + escHtml(f.context_snippet) + '</span>'
      : '';

    rows.push('<div class="' + rowClass + '">' + col1 + col2 + col3 + col4 + col5 + snippet + '</div>');
  }
  body.innerHTML = rows.join('');
}

function filterFindings() {
  const batch = state.batches[state.activeBatchId];
  if (!batch) return;
  const search = document.getElementById('review-search').value.toLowerCase();
  const tf = document.getElementById('review-type-filter').value;
  renderFindings(batch.findings.filter(f =>
    (!tf || f.entity_type === tf) &&
    (!search || f.original_value.toLowerCase().includes(search))
  ));
}

function setFindingAction(findingId, action) {
  const batch = state.batches[state.activeBatchId];
  if (!batch) return;
  const f = batch.findings.find(f => f.finding_id === findingId);
  if (f) { f._action = action; filterFindings(); }
}

function updatePseudonym(findingId, value) {
  const batch = state.batches[state.activeBatchId];
  if (!batch) return;
  const f = batch.findings.find(f => f.finding_id === findingId);
  if (f) {
    f.proposed_pseudonym = value;
    f._action = 'modify';
    f._modified = true;
    // Aggiorna solo le classi della riga senza ri-renderizzare (preserva il focus sull'input)
    const rows = document.querySelectorAll('#drawer-review-body .finding-row');
    rows.forEach(row => {
      const inp = row.querySelector('.finding-pseudonym-input');
      if (inp && inp.dataset.fid === findingId) {
        row.classList.add('finding-modified');
        row.classList.remove('finding-rejected');
      }
    });
  }
}

function removeFinding(findingId) {
  const batch = state.batches[state.activeBatchId];
  if (!batch) return;
  batch.findings = batch.findings.filter(f => f.finding_id !== findingId);
  filterFindings();
}

function acceptAllFindings() {
  const batch = state.batches[state.activeBatchId];
  if (!batch) return;
  batch.findings.forEach(f => f._action = 'accept');
  filterFindings();
}

function rejectAllFindings() {
  const batch = state.batches[state.activeBatchId];
  if (!batch) return;
  batch.findings.forEach(f => f._action = 'reject');
  filterFindings();
}

// ─── DRAWER ──────────────────────────────────────────────────────────────────

function openDrawer(name) {
  document.querySelectorAll('.drawer').forEach(d => d.classList.remove('open'));
  document.getElementById('drawer-overlay').classList.add('active');
  const el = document.getElementById('drawer-' + name);
  if (el) el.classList.add('open');
}

function closeDrawer() {
  document.querySelectorAll('.drawer').forEach(d => d.classList.remove('open'));
  document.getElementById('drawer-overlay').classList.remove('active');
}

// ─── PASSPHRASE ──────────────────────────────────────────────────────────────

function showPassphraseModal(pp) {
  if (!pp) return;
  document.getElementById('modal-passphrase-value').textContent = pp;
  document.getElementById('modal-passphrase').style.display = 'flex';
  const el = document.getElementById('passphrase-value');
  if (el) {
    el.textContent = pp;
    el.classList.remove('passphrase-hidden');
    state.passphraseVisible = true;
  }
}

function closePassphraseModal() {
  document.getElementById('modal-passphrase').style.display = 'none';
}

function copyModalPassphrase() {
  const pp = document.getElementById('modal-passphrase-value').textContent;
  navigator.clipboard.writeText(pp)
    .then(() => toast('Passphrase copiata.', 'success'))
    .catch(() => {});
}

function togglePassphraseVisibility() {
  const el = document.getElementById('passphrase-value');
  if (!el) return;
  state.passphraseVisible = !state.passphraseVisible;
  if (state.passphraseVisible) {
    el.textContent = state.currentPassphrase || '—';
    el.classList.remove('passphrase-hidden');
  } else {
    el.textContent = '••••••••••••••••••••••••';
    el.classList.add('passphrase-hidden');
  }
}

function copyPassphrase() {
  if (!state.currentPassphrase) { toast('Nessuna passphrase.', 'warning'); return; }
  navigator.clipboard.writeText(state.currentPassphrase)
    .then(() => toast('Passphrase copiata.', 'success'))
    .catch(() => {});
}

async function regeneratePassphrase() {
  const batchId = state.activeBatchId;
  if (!batchId) { toast('Nessun batch attivo.', 'warning'); return; }
  try {
    const r = await fetch(API + '/api/batches/' + batchId + '/passphrase/regenerate', { method: 'POST' });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    state.currentPassphrase = data.passphrase;
    if (state.batches[batchId]) state.batches[batchId].passphrase = data.passphrase;
    showPassphraseModal(data.passphrase);
    toast('Passphrase rigenerata.', 'success');
  } catch (err) {
    toast('Errore: ' + err.message, 'error');
  }
}

// ─── SETTINGS: DIZIONARI ─────────────────────────────────────────────────────

async function loadDictStatus() {
  try {
    const r = await fetch(API + '/api/settings/dictionaries');
    if (!r.ok) return;
    const d = await r.json();
    const el = document.getElementById('dict-status');
    if (el) el.textContent = (d.total_terms || 0) + ' termini in ' + (d.files || 0) + ' file';
  } catch {}
}

async function reloadDictionaries() {
  try {
    const r = await fetch(API + '/api/settings/dictionaries/reload', { method: 'POST' });
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    const el = document.getElementById('dict-status');
    if (el) el.textContent = (d.total_terms || 0) + ' termini in ' + (d.files || 0) + ' file';
    toast('Dizionari ricaricati: ' + (d.total_terms || 0) + ' termini.', 'success');
  } catch (err) {
    toast('Errore: ' + err.message, 'error');
  }
}

// ─── SETTINGS: LDAP ──────────────────────────────────────────────────────────

function toggleLdapSection() {
  const enabled = document.getElementById('ldap-enabled').checked;
  document.getElementById('ldap-config-section').style.display = enabled ? 'block' : 'none';
}

function restoreLdapConfig() {
  try {
    const cfg = JSON.parse(localStorage.getItem(LS_LDAP) || 'null');
    if (!cfg) return;
    const setVal = (id, val) => { const el = document.getElementById(id); if (el) { if (el.type === 'checkbox') el.checked = !!val; else el.value = val || ''; } };
    setVal('ldap-enabled', cfg.enabled);
    setVal('ldap-host', cfg.host);
    setVal('ldap-port', cfg.port || 389);
    setVal('ldap-tls', cfg.use_tls);
    setVal('ldap-starttls', cfg.use_starttls);
    setVal('ldap-bind-dn', cfg.bind_dn);
    setVal('ldap-base-dn', cfg.base_dn);
    setVal('ldap-filter', cfg.search_filter);
    // NON ripristinare la password per sicurezza
    toggleLdapSection();
  } catch {}
}

async function saveLdapConfig() {
  const cfg = {
    enabled: document.getElementById('ldap-enabled').checked,
    host: document.getElementById('ldap-host').value,
    port: parseInt(document.getElementById('ldap-port').value) || 389,
    use_tls: document.getElementById('ldap-tls').checked,
    use_starttls: document.getElementById('ldap-starttls').checked,
    bind_dn: document.getElementById('ldap-bind-dn').value,
    bind_password: document.getElementById('ldap-bind-password').value,
    base_dn: document.getElementById('ldap-base-dn').value,
    search_filter: document.getElementById('ldap-filter').value,
  };
  try {
    const r = await fetch(API + '/api/settings/ldap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg),
    });
    if (!r.ok) throw new Error(await r.text());
    // Salva in localStorage senza password
    const cfgNoPass = Object.assign({}, cfg, { bind_password: '' });
    localStorage.setItem(LS_LDAP, JSON.stringify(cfgNoPass));
    toast('Configurazione LDAP salvata.', 'success');
  } catch (err) {
    toast('Errore: ' + err.message, 'error');
  }
}

async function testLdapConnection() {
  const resultEl = document.getElementById('ldap-test-result');
  const diagEl = document.getElementById('ldap-diagnostics-panel');
  resultEl.style.display = 'block';
  resultEl.textContent = '⏳ Test in corso...';
  resultEl.className = 'ldap-test-result';
  if (diagEl) diagEl.style.display = 'none';
  try {
    const r = await fetch(API + '/api/settings/ldap/test', { method: 'POST' });
    const d = await r.json();
    resultEl.className = 'ldap-test-result ' + (d.ok ? 'ldap-ok' : 'ldap-error');
    if (d.ok) {
      resultEl.textContent = '✓ OK — ' + d.user_count + ' utenti';
      if (d.diagnostics) {
        resultEl.textContent += ' (' + (d.diagnostics.pages_count || 1) + ' pagine, ' +
          (d.diagnostics.elapsed_ms || 0) + 'ms)';
        if (diagEl) renderLdapDiagnostics(d.diagnostics, diagEl);
      }
    } else {
      resultEl.textContent = '✗ ' + (d.error || 'Fallito');
      if (d.diagnostics) {
        if (d.diagnostics.error) resultEl.textContent += ' — ' + d.diagnostics.error;
        if (diagEl) renderLdapDiagnostics(d.diagnostics, diagEl);
      }
    }
  } catch (err) {
    resultEl.className = 'ldap-test-result ldap-error';
    resultEl.textContent = '✗ ' + err.message;
  }
}

async function refreshLdapCache() {
  try {
    const r = await fetch(API + '/api/settings/ldap/refresh', { method: 'POST' });
    const d = await r.json();
    toast(d.ok ? 'Cache LDAP aggiornata.' : 'Errore: ' + d.message, d.ok ? 'success' : 'error');
  } catch (err) {
    toast('Errore: ' + err.message, 'error');
  }
}

// ─── DRAG-AND-DROP DIRETTO ──────────────────────────────────────────────────

async function handleFileUploadDirect(files) {
  if (state.sourceMode !== 'file') {
    toast('Modalità corrente: Console. Passa a File per drag-and-drop.', 'warning');
    return;
  }
  if (!files || !files.length) return;
  for (const file of files) {
    const cardEl = createBatchCard(null, file.name, 'uploading');
    try {
      const fd = new FormData();
      fd.append('files', file);
      fd.append('mode', state.mode);
      fd.append('preset', state.preset);
      const r = await fetch(API + '/api/batches', { method: 'POST', body: fd });
      if (!r.ok) {
        let msg = 'Errore ' + r.status;
        try { const e = await r.json(); msg = e.detail || JSON.stringify(e); } catch {}
        throw new Error(msg);
      }
      const data = await r.json();
      const batchId = data.batch_id;
      cardEl.dataset.batchId = batchId;
      state.batches[batchId] = {
        id: batchId, label: file.name, mode: state.mode, status: 'review',
        findings: data.findings || [], inputText: null,
        fileId: data.files && data.files.length > 0 ? data.files[0].id : null,
        passphrase: data.passphrase, createdAt: new Date().toISOString(),
      };
      state.activeBatchId = batchId;
      state.currentPassphrase = data.passphrase;
      updateCardReady(cardEl, batchId, data);
      addToSidebar(batchId, file.name, (data.findings || []).length);
      saveSessionHistory(batchId, file.name, (data.findings || []).length);
      showPassphraseModal(data.passphrase);
    } catch (err) {
      updateCardError(cardEl, err.message);
      toast('Errore upload ' + file.name + ': ' + err.message, 'error');
    }
  }
}

// ─── SIDEBAR RENAME INLINE ───────────────────────────────────────────────────

function startRename(batchId, event) {
  event.stopPropagation();
  const item = document.getElementById('sidebar-' + batchId);
  if (!item) return;
  const labelEl = item.querySelector('.sidebar-item-label');
  const currentLabel = labelEl ? labelEl.textContent : batchId.slice(0, 8);
  const input = document.createElement('input');
  input.className = 'sidebar-item-rename-input';
  input.value = currentLabel;
  input.onclick = e => e.stopPropagation();
  input.onkeydown = e => {
    if (e.key === 'Enter') { commitRename(batchId, input.value); }
    if (e.key === 'Escape') { renderSidebarItem(batchId); }
  };
  input.onblur = () => commitRename(batchId, input.value);
  if (labelEl) labelEl.replaceWith(input);
  input.focus(); input.select();
}

function commitRename(batchId, newLabel) {
  const label = (newLabel || '').trim() || batchId.slice(0, 8);
  if (state.batches[batchId]) state.batches[batchId].label = label;
  // Aggiorna anche la card
  const card = document.querySelector('[data-batch-id="' + batchId + '"]');
  if (card) { const cl = card.querySelector('.card-label'); if (cl) cl.textContent = label; }
  renderSidebarItem(batchId);
}

function renderSidebarItem(batchId) {
  const item = document.getElementById('sidebar-' + batchId);
  if (!item) return;
  const batch = state.batches[batchId];
  const label = (batch && batch.label) || batchId.slice(0, 8);
  const count = (batch && batch.findings) ? batch.findings.length : 0;
  const now = batch && batch.createdAt ? new Date(batch.createdAt) : new Date();
  const timeStr = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');
  item.innerHTML =
    '<div class="sidebar-item-row">' +
      '<span class="sidebar-item-label" title="' + escHtml(label) + '">' + escHtml(label) + '</span>' +
      '<span class="sidebar-item-count" id="sidebar-count-' + batchId + '">' + count + '</span>' +
      '<button class="icon-btn-sm" onclick="startRename(\'' + batchId + '\', event)" title="Rinomina">&#x270F;</button>' +
    '</div>' +
    '<div class="sidebar-item-meta"><span class="sidebar-item-time">' + timeStr + '</span></div>';
}

// ─── LDAP DIAGNOSTICS PANEL ──────────────────────────────────────────────────

function renderLdapDiagnostics(diag, container) {
  if (!diag || !container) return;
  const rows = [
    ['Utenti caricati', diag.users_loaded, diag.users_loaded > 0 ? 'ok' : 'warn'],
    ['Pagine LDAP', diag.pages_count, ''],
    ['Tempo (ms)', diag.elapsed_ms, ''],
    ['Stato', diag.status || 'n/a', diag.status === 'ok' ? 'ok' : 'warn'],
    ['Errore', diag.error || '—', diag.error ? 'err' : ''],
  ];
  container.innerHTML = rows.map(([k, v, cls]) =>
    '<div class="ldap-diag-row">' +
      '<span class="ldap-diag-key">' + escHtml(k) + '</span>' +
      '<span class="ldap-diag-val ' + cls + '">' + escHtml(String(v != null ? v : '—')) + '</span>' +
    '</div>'
  ).join('');
  container.style.display = 'block';
}

// ─── TOAST ───────────────────────────────────────────────────────────────────

function toast(msg, type) {
  if (!type) type = 'info';
  const container = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = 'toast toast-' + type;
  t.textContent = msg;
  container.appendChild(t);
  setTimeout(() => {
    t.classList.add('toast-fade');
    setTimeout(() => t.remove(), 400);
  }, 3500);
}

// ─── UTILITY ─────────────────────────────────────────────────────────────────

function escHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
