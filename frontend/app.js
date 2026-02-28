/**
 * Local Pseudonymization Tool — Frontend Application
 * Vanilla JavaScript SPA, nessuna dipendenza esterna.
 * Tutte le chiamate API sono dirette a 127.0.0.1:8000 (localhost).
 */

'use strict';

// ─── Stato Applicazione ──────────────────────────────────────────────────────

const state = {
    files: [],          // File selezionati dall'utente
    batchId: null,      // ID del batch corrente
    findings: [],       // Finding restituiti dal backend
    filteredFindings: [], // Finding dopo i filtri
    fileMap: {},        // file_id -> original_name
    decisions: {},      // finding_id -> { action, modified_pseudonym }
};

// ─── Utility ─────────────────────────────────────────────────────────────────

const API_BASE = window.location.origin + '/api';

async function apiCall(method, path, body = null, isFormData = false) {
    const opts = { method };
    if (body) {
        if (isFormData) {
            opts.body = body;
        } else {
            opts.headers = { 'Content-Type': 'application/json' };
            opts.body = JSON.stringify(body);
        }
    }
    const resp = await fetch(API_BASE + path, opts);
    if (!resp.ok) {
        let errMsg = `HTTP ${resp.status}`;
        try {
            const err = await resp.json();
            errMsg = err.detail || errMsg;
        } catch (_) {}
        throw new Error(errMsg);
    }
    return resp.json();
}

function showToast(msg, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function showStep(stepId) {
    document.querySelectorAll('.step').forEach(s => {
        s.classList.remove('active');
        s.classList.add('hidden');
    });
    const target = document.getElementById(stepId);
    if (target) {
        target.classList.remove('hidden');
        target.classList.add('active');
    }
}

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function getFileIcon(name) {
    const ext = name.split('.').pop().toLowerCase();
    const icons = {
        txt: '📄', md: '📝', csv: '📊', docx: '📘', pdf: '📕',
        xlsx: '📗', jpg: '🖼️', jpeg: '🖼️', png: '🖼️',
    };
    return icons[ext] || '📄';
}

// ─── Gestione File ────────────────────────────────────────────────────────────

const SUPPORTED_EXTS = ['txt', 'md', 'csv', 'docx', 'pdf', 'xlsx', 'jpg', 'jpeg', 'png'];

function addFiles(newFiles) {
    for (const file of newFiles) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (!SUPPORTED_EXTS.includes(ext)) {
            showToast(`Formato non supportato: ${file.name}`, 'warning');
            continue;
        }
        if (file.size > 50 * 1024 * 1024) {
            showToast(`File troppo grande (max 50 MB): ${file.name}`, 'warning');
            continue;
        }
        // Evita duplicati
        if (!state.files.find(f => f.name === file.name && f.size === file.size)) {
            state.files.push(file);
        }
    }
    renderFileList();
    updateScanButton();
}

function removeFile(index) {
    state.files.splice(index, 1);
    renderFileList();
    updateScanButton();
}

function renderFileList() {
    const container = document.getElementById('file-list');
    if (state.files.length === 0) {
        container.classList.add('hidden');
        return;
    }
    container.classList.remove('hidden');
    container.innerHTML = state.files.map((f, i) => `
        <div class="file-item">
            <span class="file-icon">${getFileIcon(f.name)}</span>
            <span class="file-name">${escapeHtml(f.name)}</span>
            <span class="file-size">${formatBytes(f.size)}</span>
            <button class="file-remove" onclick="removeFile(${i})" title="Rimuovi">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>
    `).join('');
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ─── Passphrase Strength ──────────────────────────────────────────────────────

function checkPasswordStrength(pw) {
    const bar = document.getElementById('pw-strength');
    if (!pw) { bar.className = 'pw-strength'; bar.style.width = '0'; return; }
    let score = 0;
    if (pw.length >= 8) score++;
    if (pw.length >= 14) score++;
    if (/[A-Z]/.test(pw)) score++;
    if (/[0-9]/.test(pw)) score++;
    if (/[^a-zA-Z0-9]/.test(pw)) score++;
    if (score <= 2) bar.className = 'pw-strength weak';
    else if (score <= 3) bar.className = 'pw-strength medium';
    else bar.className = 'pw-strength strong';
}

function updateScanButton() {
    const btn = document.getElementById('btn-scan');
    const pw = document.getElementById('passphrase').value;
    btn.disabled = state.files.length === 0 || pw.length < 4;
}

// ─── Drag & Drop ──────────────────────────────────────────────────────────────

function initDropZone() {
    const zone = document.getElementById('drop-zone');

    zone.addEventListener('click', () => document.getElementById('file-input').click());
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        addFiles(Array.from(e.dataTransfer.files));
    });

    document.getElementById('file-input').addEventListener('change', e => {
        addFiles(Array.from(e.target.files));
        e.target.value = ''; // Reset per permettere ri-selezione dello stesso file
    });
}

// ─── Scansione ────────────────────────────────────────────────────────────────

async function startScan() {
    const pw = document.getElementById('passphrase').value;
    const mode = document.querySelector('input[name="mode"]:checked').value;
    const isDryRun = document.getElementById('dry-run').checked;

    if (!pw || pw.length < 4) {
        showToast('Inserisci una passphrase di almeno 4 caratteri.', 'error');
        return;
    }

    showStep('step-scanning');
    document.getElementById('scan-status-msg').textContent = 'Caricamento file...';
    document.getElementById('progress-bar').style.width = '20%';

    try {
        // Crea il FormData con i file e la configurazione
        const formData = new FormData();
        for (const file of state.files) {
            formData.append('files', file, file.name);
        }
        formData.append('mode', mode);
        formData.append('is_dry_run', isDryRun ? 'true' : 'false');
        formData.append('passphrase', pw);

        // Crea il batch e carica i file
        document.getElementById('scan-status-msg').textContent = 'Creazione batch e upload file...';
        document.getElementById('progress-bar').style.width = '35%';

        const batchData = await apiCall('POST', '/batches', formData, true);
        state.batchId = batchData.batch_id;

        // Costruisci la mappa file_id -> nome
        state.fileMap = {};
        for (const fr of batchData.files) {
            state.fileMap[fr.file_id] = fr.original_name;
        }

        // Avvia la scansione
        document.getElementById('scan-status-msg').textContent = 'Analisi dei file in corso...';
        document.getElementById('progress-bar').style.width = '60%';

        const scanResult = await apiCall('POST', `/batches/${state.batchId}/scan`);

        document.getElementById('progress-bar').style.width = '90%';
        document.getElementById('scan-status-msg').textContent = `Trovati ${scanResult.findings_count} potenziali dati sensibili.`;

        // Recupera i finding
        const findingsData = await apiCall('GET', `/batches/${state.batchId}/findings`);
        state.findings = findingsData.findings;

        document.getElementById('progress-bar').style.width = '100%';

        setTimeout(() => {
            renderReviewStep(batchData.files);
            showStep('step-review');
        }, 500);

    } catch (err) {
        document.getElementById('error-message').textContent = `Errore durante la scansione: ${err.message}`;
        showStep('step-error');
        showToast(`Errore: ${err.message}`, 'error');
    }
}

// ─── Review ───────────────────────────────────────────────────────────────────

function renderReviewStep(fileRecords) {
    // Popola il filtro file
    const filterFile = document.getElementById('filter-file');
    filterFile.innerHTML = '<option value="">Tutti i file</option>';
    for (const fr of fileRecords) {
        const opt = document.createElement('option');
        opt.value = fr.file_id;
        opt.textContent = fr.original_name;
        filterFile.appendChild(opt);
    }

    // Inizializza le decisioni (tutte "accept" di default)
    state.decisions = {};
    for (const f of state.findings) {
        state.decisions[f.finding_id] = { action: 'accept', modified_pseudonym: null };
    }

    applyFiltersAndRender();
}

function applyFiltersAndRender() {
    const typeFilter = document.getElementById('filter-type').value;
    const fileFilter = document.getElementById('filter-file').value;
    const searchFilter = document.getElementById('filter-search').value.toLowerCase();

    state.filteredFindings = state.findings.filter(f => {
        if (typeFilter && f.entity_type !== typeFilter) return false;
        if (fileFilter && f.file_id !== fileFilter) return false;
        if (searchFilter) {
            const inOriginal = f.original_value.toLowerCase().includes(searchFilter);
            const inPseudo = f.proposed_pseudonym.toLowerCase().includes(searchFilter);
            if (!inOriginal && !inPseudo) return false;
        }
        return true;
    });

    renderFindingsTable();
    updateReviewCounter();
}

function renderFindingsTable() {
    const tbody = document.getElementById('findings-tbody');
    const noMsg = document.getElementById('no-findings-msg');

    if (state.filteredFindings.length === 0) {
        tbody.innerHTML = '';
        noMsg.classList.remove('hidden');
        return;
    }

    noMsg.classList.add('hidden');

    tbody.innerHTML = state.filteredFindings.map(f => {
        const dec = state.decisions[f.finding_id] || { action: 'accept', modified_pseudonym: null };
        const fileName = state.fileMap[f.file_id] || f.file_id;
        const location = f.location;
        let sourceRef = fileName;
        if (location.line) sourceRef += `:${location.line}`;
        if (location.cell_ref) sourceRef += ` (${location.cell_ref})`;

        const confClass = f.confidence_score >= 0.9 ? 'conf-high' : f.confidence_score >= 0.7 ? 'conf-medium' : 'conf-low';
        const confPct = Math.round(f.confidence_score * 100);

        const rowClass = dec.action === 'reject' ? 'rejected' : dec.action === 'modify' ? 'modified' : '';
        const selectClass = dec.action === 'accept' ? 'accepted' : dec.action === 'reject' ? 'rejected' : 'modified';

        const modifyInput = dec.action === 'modify' ? `
            <input type="text" class="modify-input"
                value="${escapeHtml(dec.modified_pseudonym || f.proposed_pseudonym)}"
                placeholder="Inserisci pseudonimo personalizzato..."
                onchange="updateModifiedPseudonym('${f.finding_id}', this.value)"
                oninput="updateModifiedPseudonym('${f.finding_id}', this.value)">
        ` : '';

        return `
        <tr class="${rowClass}" data-finding-id="${f.finding_id}">
            <td><span class="entity-badge badge-${f.entity_type}">${f.entity_type}</span></td>
            <td><span class="original-value" title="${escapeHtml(f.original_value)}">${escapeHtml(f.original_value)}</span></td>
            <td>
                <span class="pseudonym-value">${escapeHtml(dec.action === 'modify' && dec.modified_pseudonym ? dec.modified_pseudonym : f.proposed_pseudonym)}</span>
            </td>
            <td style="font-size:0.8rem;color:var(--text-muted);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(sourceRef)}">${escapeHtml(sourceRef)}</td>
            <td>
                <div class="conf-bar-wrap ${confClass}">
                    <div class="conf-bar"><div class="conf-bar-fill" style="width:${confPct}%"></div></div>
                    <span class="conf-label">${confPct}%</span>
                </div>
            </td>
            <td>
                <select class="action-select ${selectClass}"
                    onchange="updateDecision('${f.finding_id}', this.value)">
                    <option value="accept" ${dec.action === 'accept' ? 'selected' : ''}>✓ Accetta</option>
                    <option value="reject" ${dec.action === 'reject' ? 'selected' : ''}>✗ Escludi</option>
                    <option value="modify" ${dec.action === 'modify' ? 'selected' : ''}>✎ Modifica</option>
                </select>
                ${modifyInput}
            </td>
        </tr>`;
    }).join('');
}

function updateDecision(findingId, action) {
    if (!state.decisions[findingId]) {
        state.decisions[findingId] = { action: 'accept', modified_pseudonym: null };
    }
    state.decisions[findingId].action = action;
    if (action !== 'modify') {
        state.decisions[findingId].modified_pseudonym = null;
    }
    applyFiltersAndRender();
}

function updateModifiedPseudonym(findingId, value) {
    if (!state.decisions[findingId]) {
        state.decisions[findingId] = { action: 'modify', modified_pseudonym: value };
    } else {
        state.decisions[findingId].modified_pseudonym = value;
    }
}

function updateReviewCounter() {
    const total = state.findings.length;
    const accepted = Object.values(state.decisions).filter(d => d.action === 'accept').length;
    const rejected = Object.values(state.decisions).filter(d => d.action === 'reject').length;
    const modified = Object.values(state.decisions).filter(d => d.action === 'modify').length;
    document.getElementById('review-counter').textContent =
        `${total} totali — ${accepted} accettati — ${modified} modificati — ${rejected} esclusi`;
}

function acceptAll() {
    for (const fid of Object.keys(state.decisions)) {
        state.decisions[fid] = { action: 'accept', modified_pseudonym: null };
    }
    applyFiltersAndRender();
    showToast('Tutti i finding accettati.', 'success');
}

function rejectAll() {
    for (const fid of Object.keys(state.decisions)) {
        state.decisions[fid] = { action: 'reject', modified_pseudonym: null };
    }
    applyFiltersAndRender();
    showToast('Tutti i finding esclusi.', 'warning');
}

// ─── Applicazione ─────────────────────────────────────────────────────────────

async function applyBatch() {
    try {
        // Invia le decisioni di review
        const decisions = Object.entries(state.decisions).map(([finding_id, dec]) => ({
            finding_id,
            action: dec.action,
            modified_pseudonym: dec.modified_pseudonym || null,
        }));

        await apiCall('POST', `/batches/${state.batchId}/review`, { decisions });

        // Applica le trasformazioni
        showToast('Applicazione trasformazioni in corso...', 'info');
        await apiCall('POST', `/batches/${state.batchId}/apply`);

        // Recupera il batch per le statistiche
        const batchStatus = await apiCall('GET', `/batches/${state.batchId}`);

        renderDoneStep(batchStatus);
        showStep('step-done');
        showToast('Batch completato con successo!', 'success');

    } catch (err) {
        document.getElementById('error-message').textContent = `Errore durante l'applicazione: ${err.message}`;
        showStep('step-error');
        showToast(`Errore: ${err.message}`, 'error');
    }
}

// ─── Done ─────────────────────────────────────────────────────────────────────

function renderDoneStep(batchStatus) {
    const accepted = Object.values(state.decisions).filter(d => d.action === 'accept').length;
    const modified = Object.values(state.decisions).filter(d => d.action === 'modify').length;
    const applied = accepted + modified;

    document.getElementById('done-summary').innerHTML = `
        <div class="done-stats">
            <div class="done-stat"><div class="value">${batchStatus.files.length}</div><div class="label">File Processati</div></div>
            <div class="done-stat"><div class="value">${state.findings.length}</div><div class="label">Entità Rilevate</div></div>
            <div class="done-stat"><div class="value">${applied}</div><div class="label">Sostituzioni Applicate</div></div>
            <div class="done-stat"><div class="value">${Object.values(state.decisions).filter(d => d.action === 'reject').length}</div><div class="label">Finding Esclusi</div></div>
        </div>
    `;

    const batchId = state.batchId;
    document.getElementById('download-grid').innerHTML = `
        <button class="btn-download primary" onclick="downloadZip()">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
            Scarica File Pseudonimizzati (.zip)
        </button>
        <button class="btn-download" onclick="downloadReport('html')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            Report HTML
        </button>
        <button class="btn-download" onclick="downloadReport('json')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            Report JSON
        </button>
    `;
}

async function downloadZip() {
    try {
        const resp = await fetch(`${API_BASE}/batches/${state.batchId}/download`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `pseudonymized_batch_${state.batchId.substring(0, 8)}.zip`;
        a.click();
        URL.revokeObjectURL(url);
        showToast('Download avviato.', 'success');
    } catch (err) {
        showToast(`Errore download: ${err.message}`, 'error');
    }
}

async function downloadReport(format) {
    try {
        const resp = await fetch(`${API_BASE}/batches/${state.batchId}/report/${format}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `report.${format}`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        showToast(`Errore download report: ${err.message}`, 'error');
    }
}

// ─── Reset ────────────────────────────────────────────────────────────────────

function resetApp() {
    state.files = [];
    state.batchId = null;
    state.findings = [];
    state.filteredFindings = [];
    state.fileMap = {};
    state.decisions = {};

    document.getElementById('file-list').classList.add('hidden');
    document.getElementById('file-list').innerHTML = '';
    document.getElementById('passphrase').value = '';
    document.getElementById('dry-run').checked = false;
    document.querySelector('input[name="mode"][value="light"]').checked = true;
    document.getElementById('pw-strength').className = 'pw-strength';
    document.getElementById('btn-scan').disabled = true;
    document.getElementById('filter-type').value = '';
    document.getElementById('filter-file').innerHTML = '<option value="">Tutti i file</option>';
    document.getElementById('filter-search').value = '';

    showStep('step-upload');
}

// ─── Inizializzazione ─────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initDropZone();

    // Passphrase
    document.getElementById('passphrase').addEventListener('input', e => {
        checkPasswordStrength(e.target.value);
        updateScanButton();
    });

    // Toggle visibilità passphrase
    document.getElementById('toggle-pw').addEventListener('click', () => {
        const input = document.getElementById('passphrase');
        input.type = input.type === 'password' ? 'text' : 'password';
    });

    // Pulsante scansione
    document.getElementById('btn-scan').addEventListener('click', startScan);

    // Filtri review
    document.getElementById('filter-type').addEventListener('change', applyFiltersAndRender);
    document.getElementById('filter-file').addEventListener('change', applyFiltersAndRender);
    document.getElementById('filter-search').addEventListener('input', applyFiltersAndRender);

    // Azioni bulk review
    document.getElementById('btn-accept-all').addEventListener('click', acceptAll);
    document.getElementById('btn-reject-all').addEventListener('click', rejectAll);

    // Applica modifiche
    document.getElementById('btn-apply').addEventListener('click', applyBatch);

    // Pulsanti di reset
    document.getElementById('btn-back-to-upload').addEventListener('click', resetApp);
    document.getElementById('btn-new-batch').addEventListener('click', resetApp);
    document.getElementById('btn-retry').addEventListener('click', resetApp);

    showStep('step-upload');
});

// Esponi funzioni globali usate dagli handler inline
window.removeFile = removeFile;
window.updateDecision = updateDecision;
window.updateModifiedPseudonym = updateModifiedPseudonym;
window.downloadZip = downloadZip;
window.downloadReport = downloadReport;
