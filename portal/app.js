/* =====================================================
   Solvit Valuation Portal — application logic
   Wired to real backend API
   ===================================================== */

const REASON_LABELS = {
  not_picking: 'Not picking', unreachable: 'Unreachable', not_ready: 'Not ready',
  call_back:   'Call back',
  no_logbook:  'No logbook',  no_sticker:  'No sticker',  no_letter:  'No letter'
};
const REASON_CLASS  = {
  not_picking: 'reason-not-picking', unreachable: 'reason-unreachable', not_ready: 'reason-not-ready',
  call_back:   'reason-call-back',
  no_logbook:  'reason-no-logbook',  no_sticker:  'reason-no-sticker',  no_letter: 'reason-no-letter'
};

const PHASE_LABEL = { 1: 'Scheduling', 2: 'Inspection', 3: 'Approval' };

const STATE = { jobs: [], activity: [], feed: [], kpis: {}, charts: {} };

/* =====================================================
   TOAST NOTIFICATIONS
   ===================================================== */

function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(container);
  }
  const colors = { info: '#2E5FAE', success: '#1F7A4D', warning: '#B07415', error: '#B83434' };
  const toast = document.createElement('div');
  toast.style.cssText = `background:${colors[type]||colors.info};color:#fff;padding:12px 18px;border-radius:8px;font-size:13px;font-family:var(--font-body);box-shadow:0 4px 12px rgba(0,0,0,0.2);max-width:320px;line-height:1.4;opacity:1;transition:opacity 0.3s;`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 4000);
}
window.showToast = showToast;

/* =====================================================
   LOGIN / LOGOUT
   ===================================================== */

function showLoginView() {
  document.getElementById('login-view').style.display = 'flex';
  document.getElementById('app').style.display = 'none';
}
window.showLoginView = showLoginView;

document.getElementById('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = e.target.querySelector('button[type="submit"]');
  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl    = document.getElementById('login-error');

  btn.textContent = 'Signing in…';
  btn.disabled = true;
  if (errEl) errEl.textContent = '';

  try {
    const user = await API.login(email, password);
    document.getElementById('login-view').style.display = 'none';
    document.getElementById('app').style.display = 'grid';
    if (document.getElementById('user-name')) document.getElementById('user-name').textContent = user.name || email;
    await init();
  } catch (err) {
    if (errEl) {
      errEl.textContent = err.message;
    } else {
      showToast(err.message, 'error');
    }
  } finally {
    btn.textContent = 'Sign in';
    btn.disabled = false;
  }
});

document.getElementById('logout-btn').addEventListener('click', () => {
  API.logout();
  showLoginView();
});

/* =====================================================
   NAVIGATION
   ===================================================== */

document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-' + btn.dataset.view).classList.add('active');
    if (btn.dataset.view === 'settings') { loadIntegrationStatus(); loadSolvers(); }
    if (btn.dataset.view === 'rules') { loadRules(); loadTemplates(); }
    if (btn.dataset.view === 'conversion') loadConversion();
    if (btn.dataset.view === 'uploads') loadUploads();
  });
});

/* =====================================================
   INITIALIZATION
   ===================================================== */

async function init() {
  const today = new Date();
  const dateEl = document.getElementById('current-date');
  if (dateEl) dateEl.textContent = today.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  try {
    const [jobs, kpis, activity, feed] = await Promise.all([
      API.getJobs(),
      API.getKpis(),
      API.getActivity(),
      API.getLiveFeed()
    ]);

    STATE.jobs     = jobs     || [];
    STATE.kpis     = kpis     || {};
    STATE.activity = activity || [];
    STATE.feed     = feed     || [];

    renderKpis();
    renderFeed();
    renderJobs();
    renderActivity();
    bindFilters();
    bindUpload();
    updateNavCount();

    // Populate integration status (incl. sender email) on load,
    // regardless of which view is active — the cards live in the Rules view.
    loadIntegrationStatus();

    setTimeout(initCharts, 100);

    // Refresh feed every 60 seconds
    setInterval(async () => {
      const fresh = await API.getLiveFeed();
      if (fresh) { STATE.feed = fresh; renderFeed(); }
    }, 60000);

  } catch (err) {
    showToast('Failed to load data: ' + err.message, 'error');
  }
}

/* =====================================================
   KPIs
   ===================================================== */

function renderKpis() {
  const k = STATE.kpis;
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? '—'; };
  set('kpi-pending-total',   k.pending_total);
  set('kpi-pending-phase1',  k.pending_phase_1);
  set('kpi-pending-phase2',  k.pending_phase_2);
  set('kpi-emails-today',    k.emails_today);
  set('kpi-reply-rate',      k.reply_rate_7d !== undefined ? k.reply_rate_7d + '%' : '—');
  set('kpi-resolved',        k.resolved_this_week);
}

function updateNavCount() {
  const el = document.getElementById('nav-jobs-count');
  if (el) el.textContent = STATE.jobs.length;
}

/* =====================================================
   LIVE FEED
   ===================================================== */

function renderFeed() {
  const iconMap = { sent: { class: 'sent', label: '→' }, reply: { class: 'reply', label: '↩' }, resolved: { class: 'resolved', label: '✓' } };
  const el = document.getElementById('liveFeed');
  if (!el) return;

  if (!STATE.feed.length) {
    el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-tertiary);font-size:13px;">No recent activity</div>';
    return;
  }

  el.innerHTML = STATE.feed.map(item => {
    const icon = iconMap[item.type] || { class: 'sent', label: '→' };
    return `<div class="feed-item"><div class="feed-icon ${icon.class}">${icon.label}</div><div class="feed-text">${item.text}</div><div class="feed-time">${item.time}</div></div>`;
  }).join('');
}

/* =====================================================
   JOBS LIST
   ===================================================== */

function renderJobs() {
  const search = (document.getElementById('jobSearch')?.value || '').toLowerCase();
  const phase  = document.getElementById('phaseFilter')?.value || 'all';
  const reason = document.getElementById('reasonFilter')?.value || 'all';
  const status = document.getElementById('statusFilter')?.value || 'all';

  const filtered = STATE.jobs.filter(j => {
    if (search) {
      const hay = `${j.vehicle_reg} ${j.client_name} ${j.solver_name || ''}`.toLowerCase();
      if (!hay.includes(search)) return false;
    }
    if (phase  !== 'all' && j.phase  !== parseInt(phase))  return false;
    if (reason !== 'all' && j.reason !== reason)           return false;
    if (status !== 'all' && j.status !== status)           return false;
    return true;
  });

  const listEl = document.getElementById('jobsList');
  if (!listEl) return;

  if (!filtered.length) {
    listEl.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-tertiary);font-size:13px;">No jobs match your filters</div>';
    return;
  }

  listEl.innerHTML = filtered.map(j => {
    const flagged = j.flagged_manual ? '<span class="status-badge status-flagged" title="Needs manual follow-up">⚑ Manual</span>' : '';
    const noClientEmail = !j.client_email;
    const callBackOnly = j.reason === 'call_back';
    let statusBadge;
    if (j.status === 'replied') {
      statusBadge = '<span class="status-badge status-replied">Reply received</span>';
    } else if (callBackOnly || noClientEmail) {
      statusBadge = '<span class="status-badge status-awaiting" title="No client email — tracked via solver summary only">Solver only</span>';
    } else {
      statusBadge = `<span class="status-badge status-awaiting">Awaiting · ${j.emails_sent} sent</span>`;
    }

    const solverOrInitiated = j.solver_name
      ? `<div class="cell-secondary">Solver:</div><div>${j.solver_name}</div>`
      : `<div class="cell-secondary">Initiated:</div><div>${j.initiated_date || '—'}</div>`;

    const lastSent = j.last_email_sent_at ? j.last_email_sent_at.split('T')[0] || j.last_email_sent_at.split(' ')[0] : '—';
    const lastTime = j.last_email_sent_at ? (j.last_email_sent_at.split('T')[1] || j.last_email_sent_at.split(' ')[1] || '') : '';

    const reasonCell = j.phase === 3 && j.missing_documents
      ? `<span class="reason-badge ${REASON_CLASS[j.reason] || ''}" title="${j.missing_documents}">Missing docs (${j.missing_documents.split(',').length})</span>`
      : `<span class="reason-badge ${REASON_CLASS[j.reason] || ''}">${REASON_LABELS[j.reason] || j.reason || '—'}</span>`;

    return `
      <div class="table-row" data-job-id="${j.id}">
        <div><div class="cell-primary">${j.vehicle_reg}</div><div class="cell-secondary cell-mono">${j.id}</div></div>
        <div><div class="cell-primary">${j.client_name || 'Client'}</div><div class="cell-secondary">${j.client_email || (j.client_phone ? '📞 ' + j.client_phone : '—')}</div></div>
        <div><span class="phase-badge phase-${j.phase}">${PHASE_LABEL[j.phase] || '—'}</span></div>
        <div>${reasonCell}</div>
        <div><div>${lastSent}</div><div class="cell-secondary">${lastTime.substring(0,5)}</div></div>
        <div>${solverOrInitiated}</div>
        <div>${statusBadge}${flagged}</div>
      </div>`;
  }).join('');

  document.querySelectorAll('.table-row[data-job-id]').forEach(row => {
    row.addEventListener('click', () => openJobDetail(row.dataset.jobId));
  });
}

function bindFilters() {
  ['jobSearch','phaseFilter','reasonFilter','statusFilter'].forEach(id => {
    document.getElementById(id)?.addEventListener(id === 'jobSearch' ? 'input' : 'change', renderJobs);
  });
}

/* =====================================================
   JOB DETAIL MODAL
   ===================================================== */

async function openJobDetail(jobId) {
  const job = STATE.jobs.find(j => j.id === jobId);
  if (!job) return;

  const history = await API.getEmailHistory(jobId) || [];

  const historyHtml = history.length
    ? history.map(h => `
        <div class="email-history-item">
          <div class="email-history-time">${h.sent_at} · ${h.template_key || h.type || ''}</div>
          <div class="email-history-subject">${h.subject}</div>
          <div style="margin-top:4px;"><span class="status-badge status-${(h.delivery_status||h.status||'').toLowerCase()}">${h.delivery_status || h.status || ''}</span></div>
        </div>`).join('')
    : '<div style="color:var(--text-tertiary);font-size:13px;">No emails sent yet</div>';

  const resolveBtn = job.job_status === 'pending'
    ? `<button class="btn-primary" id="resolve-btn" style="margin-top:16px;">Mark as resolved</button>`
    : `<div class="status-badge status-replied" style="margin-top:16px;">Resolved</div>`;

  document.getElementById('job-modal-content').innerHTML = `
    <div class="modal-header">
      <div><h2>${job.vehicle_reg}</h2><p style="color:var(--text-secondary);font-size:13px;margin-top:2px;">Job ${job.id}</p></div>
      <button class="modal-close" id="modal-close">×</button>
    </div>
    <dl class="detail-grid">
      <dt>Client</dt><dd>${job.client_name}</dd>
      <dt>Email</dt><dd>${job.client_email}</dd>
      <dt>Phone</dt><dd>${job.client_phone || '—'}</dd>
      <dt>Phase</dt><dd>${PHASE_LABEL[job.phase] || '—'}</dd>
      <dt>Reason</dt><dd><span class="reason-badge ${REASON_CLASS[job.reason] || ''}">${REASON_LABELS[job.reason] || job.reason || '—'}</span></dd>
      ${job.phase === 3 && job.missing_documents ? `<dt>Missing</dt><dd>${job.missing_documents.split(',').map(c => `<span class="reason-badge ${REASON_CLASS[c.trim()] || ''}" style="margin-right:4px;">${REASON_LABELS[c.trim()] || c}</span>`).join('')}</dd>` : ''}
      <dt>Initiated</dt><dd>${job.initiated_date || '—'}</dd>
      ${job.scheduled_date ? `<dt>Scheduled</dt><dd>${job.scheduled_date}</dd>` : ''}
      ${job.solver_name    ? `<dt>Solver</dt><dd>${job.solver_name} · ${job.solver_phone || ''}</dd>` : ''}
      <dt>Status</dt><dd>${job.status === 'replied' ? '<span class="status-badge status-replied">Reply received</span>' : '<span class="status-badge status-awaiting">Awaiting reply</span>'}</dd>
      ${job.flagged_manual ? '<dt>Flag</dt><dd><span class="status-badge status-flagged">⚑ Needs manual follow-up (2 emails sent)</span></dd>' : ''}
    </dl>
    <div class="detail-section"><h3>Email history</h3><div class="email-history">${historyHtml}</div></div>
    ${resolveBtn}`;

  document.getElementById('job-modal').style.display = 'flex';
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.querySelector('.modal-overlay').addEventListener('click', closeModal);

  document.getElementById('resolve-btn')?.addEventListener('click', async () => {
    await API.resolveJob(jobId);
    showToast(`Job ${jobId} marked as resolved`, 'success');
    closeModal();
    const fresh = await API.getJobs();
    if (fresh) { STATE.jobs = fresh; renderJobs(); updateNavCount(); }
  });
}

function closeModal() { document.getElementById('job-modal').style.display = 'none'; }

/* =====================================================
   EMAIL ACTIVITY
   ===================================================== */

function renderActivity() {
   const el = document.getElementById('activityList');
   if (!el) return;
   
   if (!STATE.activity.length) {
      el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-tertiary);font-size:13px;">No email activity yet</div>';
      return;
   }
   
   el.innerHTML = STATE.activity.map(a => {  
      const date = (a.sent_at || '').split('T')[0] || '—';
      const rawTime = (a.sent_at || '').split('T')[1] || '';
      let time = rawTime.substring(0, 5);
      if (rawTime) {
        const d = new Date(a.sent_at);
        time = d.toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Nairobi' });
      }
      return `
      <div class="table-row table-row-activity">
        <div><div>${date}</div><div class="cell-secondary">${time.substring(0,5)}</div></div>
        <div class="cell-primary">${a.client || '—'}</div>
        <div class="cell-secondary cell-mono">${a.reg || '—'}</div>
        <div>${a.type || '—'}</div>
        <div><span class="phase-badge phase-${a.phase}">${PHASE_LABEL[a.phase] || '—'}</span></div>
        <div><span class="status-badge status-${(a.status||'').toLowerCase()}">${a.status || '—'}</span></div>
      </div>`;
   }).join('');
   const total     = STATE.activity.length;
   const delivered = STATE.activity.filter(a => a.status !== 'bounced').length;
   const rate      = total > 0 ? Math.round((delivered / total) * 100) : 0;
   
   const sentEl  = document.getElementById('email-kpi-sent');
   const delivEl = document.getElementById('email-kpi-delivered');
   const rateEl  = document.getElementById('email-kpi-rate');
   
   if (sentEl)  sentEl.textContent  = total;
   if (delivEl) delivEl.textContent = delivered;
   if (rateEl)  rateEl.textContent  = rate + '%';
}

/* =====================================================
   CSV / EXCEL UPLOAD
   ===================================================== */

function bindUpload() {
  const uploadBtn  = document.getElementById('upload-jobs-btn');
  const fileInput  = document.getElementById('upload-file-input');
  const templateBtn = document.getElementById('download-template-btn');
  const zohoBtn    = document.getElementById('zoho-sync-btn');

  uploadBtn?.addEventListener('click', () => fileInput?.click());
  templateBtn?.addEventListener('click', () => API.downloadTemplate());

  fileInput?.addEventListener('change', async e => {
    const file = e.target.files[0];
    if (!file) return;
    uploadBtn.textContent = 'Uploading…';
    uploadBtn.disabled = true;
    try {
      const result = await API.uploadJobs(file);
      if (result) {
        const phaseLabel = result.phase_label || 'jobs';
        const clearedTxt = result.cleared ? `, ${result.cleared} cleared` : '';
        let summaryTxt = '';
        if (result.solver_summary && result.solver_summary.summaries_queued > 0) {
          const s = result.solver_summary;
          summaryTxt = ` · ${s.summaries_queued} solver ${s.summaries_queued === 1 ? 'summary' : 'summaries'} queued (${s.jobs_covered} jobs)`;
          if (s.warnings && s.warnings.length) {
            summaryTxt += ` · ${s.warnings.length} solver(s) skipped`;
            setTimeout(() => {
              showToast(s.warnings[0] + (s.warnings.length > 1 ? ` (+${s.warnings.length - 1} more)` : ''), 'warning');
            }, 800);
          }
        }
        showToast(`Uploaded ${phaseLabel}: ${result.inserted} new, ${result.updated} updated, ${result.skipped} skipped${clearedTxt}${summaryTxt}`, 'success');
        const fresh = await API.getJobs();
        if (fresh) { STATE.jobs = fresh; renderJobs(); updateNavCount(); }
        const kpis = await API.getKpis();
        if (kpis) { STATE.kpis = kpis; renderKpis(); }
      }
    } catch (err) {
      showToast('Upload failed: ' + err.message, 'error');
    } finally {
      uploadBtn.textContent = 'Upload jobs (CSV / Excel)';
      uploadBtn.disabled = false;
      fileInput.value = '';
    }
  });

  zohoBtn?.addEventListener('click', async () => {
    zohoBtn.textContent = 'Syncing…';
    zohoBtn.disabled = true;
    try {
      const result = await API.triggerZohoSync();
      showToast(`Zoho sync: ${result.inserted} new, ${result.updated} updated`, 'success');
      const fresh = await API.getJobs();
      if (fresh) { STATE.jobs = fresh; renderJobs(); updateNavCount(); }
    } catch (err) {
      showToast('Zoho sync failed: ' + err.message, 'error');
    } finally {
      zohoBtn.textContent = 'Sync from Zoho now';
      zohoBtn.disabled = false;
    }
  });
}

/* =====================================================
   INTEGRATION STATUS (Settings page)
   ===================================================== */

async function loadIntegrationStatus() {
  const status = await API.getIntegrationStatus().catch(() => null);
  if (!status) return;

  const graphEl  = document.getElementById('integration-graph-status');
  const zohoEl   = document.getElementById('integration-zoho-status');
  const sourceEl = document.getElementById('integration-data-source');
  const senderEl = document.getElementById('integration-sender');

  if (senderEl) senderEl.textContent = status.sender_upn || '—';

  if (graphEl) {
    graphEl.textContent = status.graph?.status === 'connected'
      ? `✓ Connected — sending from ${status.sender_upn}`
      : `✗ Not connected — ${status.graph?.error || 'check credentials'}`;
    graphEl.style.color = status.graph?.status === 'connected' ? 'var(--success)' : 'var(--danger)';
  }
  if (zohoEl) {
    zohoEl.textContent = status.zoho?.status === 'connected'
      ? `✓ Connected — workspace ${status.zoho?.workspace_id}`
      : `✗ Not connected — ${status.zoho?.error || 'credentials not set'}`;
    zohoEl.style.color = status.zoho?.status === 'connected' ? 'var(--success)' : 'var(--danger)';
  }
  if (sourceEl) {
    sourceEl.textContent = status.data_source === 'zoho' ? 'Zoho Analytics (auto-sync every 15 min)' : 'Manual CSV / Excel upload';
  }
}

/* =====================================================
   SOLVER DIRECTORY (v1.3)
   ===================================================== */

let _solvers = [];

async function loadSolvers() {
  _solvers = await API.getSolvers().catch(() => []);
  const el = document.getElementById('solvers-list');
  if (!el) return;

  if (!_solvers.length) {
    el.innerHTML = `
      <div id="solver-add-form-anchor"></div>
      <div style="padding:24px;text-align:center;color:var(--text-tertiary);font-size:13px;border:1px dashed var(--border-default);border-radius:8px;">
        No solvers in directory yet. Add solvers manually, or upload an Inspection export that includes a <code>Solver_email</code> column to auto-populate.
      </div>`;
    return;
  }

  el.innerHTML = `
    <div id="solver-add-form-anchor"></div>
    <div class="table-card">
      <div class="table-head" style="grid-template-columns:1.4fr 1.8fr 1fr 80px 110px;">
        <div>Name</div><div>Email</div><div>Phone</div><div>Status</div><div>Actions</div>
      </div>
      <div class="table-body">
        ${_solvers.map(s => `
          <div class="table-row" style="grid-template-columns:1.4fr 1.8fr 1fr 80px 110px;cursor:default;" id="solver-row-${s.id}">
            <div class="cell-primary">${s.name}</div>
            <div class="cell-secondary">${s.email}</div>
            <div class="cell-secondary">${s.phone || '—'}</div>
            <div>${s.active
              ? '<span class="status-badge status-replied">Active</span>'
              : '<span class="status-badge status-awaiting">Inactive</span>'}</div>
            <div style="display:flex;gap:8px;">
              <button class="btn-link" onclick="editSolver(${s.id})">Edit</button>
              <button class="btn-link" onclick="deleteSolver(${s.id})" style="color:var(--danger);">Remove</button>
            </div>
          </div>`).join('')}
      </div>
    </div>`;
}

function showAddSolverForm(prefill = null) {
  const anchor = document.getElementById('solver-add-form-anchor');
  if (!anchor) return;
  const s = prefill || { id: null, name: '', email: '', phone: '', active: true };
  const editing = s.id !== null;
  anchor.innerHTML = `
    <div class="solver-form" id="solver-form">
      <h4 style="margin:0 0 12px;">${editing ? 'Edit solver' : 'Add solver'}</h4>
      <div class="solver-form-grid">
        <label>Name<input id="solver-input-name" value="${escapeAttr(s.name)}" placeholder="David Kimani"></label>
        <label>Email<input id="solver-input-email" type="email" value="${escapeAttr(s.email)}" placeholder="david.kimani@solvit.co.ke"></label>
        <label>Phone<input id="solver-input-phone" value="${escapeAttr(s.phone || '')}" placeholder="+254 7..."></label>
        <label class="solver-form-active"><input type="checkbox" id="solver-input-active" ${s.active ? 'checked' : ''}> Active</label>
      </div>
      <div style="margin-top:12px;display:flex;gap:8px;justify-content:flex-end;">
        <button class="btn-secondary" onclick="document.getElementById('solver-form').remove()">Cancel</button>
        <button class="btn-primary" onclick="saveSolver(${editing ? s.id : 'null'})">${editing ? 'Save changes' : 'Add solver'}</button>
      </div>
    </div>`;
  document.getElementById('solver-input-name').focus();
}
window.showAddSolverForm = showAddSolverForm;

function editSolver(id) {
  const s = _solvers.find(s => s.id === id);
  if (!s) return;
  showAddSolverForm(s);
}
window.editSolver = editSolver;

async function saveSolver(id) {
  const name   = document.getElementById('solver-input-name').value.trim();
  const email  = document.getElementById('solver-input-email').value.trim();
  const phone  = document.getElementById('solver-input-phone').value.trim();
  const active = document.getElementById('solver-input-active').checked;

  if (!name || !email)   { showToast('Name and email are required', 'warning'); return; }
  if (!email.includes('@')) { showToast('Invalid email address', 'warning'); return; }

  try {
    if (id) { await API.updateSolver(id, { name, email, phone, active }); showToast('Solver updated', 'success'); }
    else    { await API.addSolver({ name, email, phone, active });        showToast('Solver added', 'success'); }
    const form = document.getElementById('solver-form'); if (form) form.remove();
    loadSolvers();
  } catch (e) {
    showToast('Failed: ' + e.message, 'error');
  }
}
window.saveSolver = saveSolver;

async function deleteSolver(id) {
  const s = _solvers.find(s => s.id === id);
  if (!s) return;
  if (!confirm(`Remove ${s.name} from the directory? This won't affect past emails.`)) return;
  try {
    await API.deleteSolver(id);
    showToast('Solver removed', 'success');
    loadSolvers();
  } catch (e) {
    showToast('Failed: ' + e.message, 'error');
  }
}
window.deleteSolver = deleteSolver;

function escapeAttr(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

/* =====================================================
   CHARTS
   ===================================================== */

async function initCharts() {
  try {
    const [volumeData, reasonData] = await Promise.all([
      API.getEmailVolumeChart(),
      API.getReasonChart()
    ]);

    const volumeCtx = document.getElementById('volumeChart')?.getContext('2d');
    if (volumeCtx && volumeData) {
      STATE.charts.volume = new Chart(volumeCtx, {
        type: 'bar',
        data: {
          labels: volumeData.labels,
          datasets: [
            { label: 'First send', data: volumeData.first_send, backgroundColor: '#2E5FAE', borderRadius: 4 },
            { label: 'Follow-up',  data: volumeData.followup,   backgroundColor: '#1F7A4D', borderRadius: 4 }
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          scales: {
            y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.06)' }, ticks: { font: { size: 11 } } },
            x: { grid: { display: false }, ticks: { font: { size: 11 } } }
          },
          plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, font: { size: 12 }, padding: 12 } } }
        }
      });
    }

    const reasonCtx = document.getElementById('reasonChart')?.getContext('2d');
    if (reasonCtx && reasonData) {
      STATE.charts.reason = new Chart(reasonCtx, {
        type: 'doughnut',
        data: {
          labels: reasonData.map(r => `${r.reason} (${r.count})`),
          datasets: [{ data: reasonData.map(r => r.count), backgroundColor: ['#B07415','#B83434','#2E5FAE'], borderWidth: 0 }]
        },
        options: {
          responsive: true, maintainAspectRatio: false, cutout: '68%',
          plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, font: { size: 12 }, padding: 10 } } }
        }
      });
    }
  } catch (err) {
    console.warn('Charts failed to load:', err.message);
  }
}

/* =====================================================
   RULES
   ===================================================== */

let _rules = [];

async function loadRules() {
  const [rules, settings] = await Promise.all([
    API.getRules().catch(() => []),
    API.getPhaseSettings().catch(() => []),
  ]);
  _rules = rules;
  _phaseSettings = settings || [];
  const el = document.getElementById('rules-list');
  if (!el) return;

  if (!_rules.length) {
    el.innerHTML = '<div style="padding:20px;color:var(--text-tertiary);font-size:13px;">No rules found. Rules are seeded automatically on first load.</div>';
    return;
  }

  const scheduling = _rules.filter(r => (r.phase || 1) === 1);
  const inspection = _rules.filter(r => (r.phase || 1) === 2);
  const approval   = _rules.filter(r => (r.phase || 1) === 3);

  if (!inspection.length && !approval.length) {
    el.innerHTML = `<div class="rules-column">${scheduling.map(renderRuleCard).join('')}</div>`;
    return;
  }

  el.innerHTML = `
    <div class="rules-grid rules-grid-3">
      <div class="rules-column">
        <h3 class="rules-col-title">Scheduling</h3>
        <p class="rules-col-sub">When AM Team can't reach the client to schedule</p>
        ${renderSolverSummaryToggle(1)}
        ${scheduling.map(renderRuleCard).join('') || '<div class="rules-empty">No rules</div>'}
      </div>
      <div class="rules-column">
        <h3 class="rules-col-title">Inspection</h3>
        <p class="rules-col-sub">When the Solver can't confirm the inspection appointment</p>
        ${renderSolverSummaryToggle(2)}
        ${inspection.map(renderRuleCard).join('') || '<div class="rules-empty">No rules</div>'}
      </div>
      <div class="rules-column">
        <h3 class="rules-col-title">Approval</h3>
        <p class="rules-col-sub">When client documents are missing for report approval</p>
        ${renderSolverSummaryToggle(3)}
        ${approval.map(renderRuleCard).join('') || '<div class="rules-empty">No rules</div>'}
      </div>
    </div>`;
}

let _phaseSettings = [];

function renderSolverSummaryToggle(phase) {
  const setting = _phaseSettings.find(s => s.phase === phase) || { solver_summary_enabled: false };
  const checked = setting.solver_summary_enabled ? 'checked' : '';
  return `
    <div class="phase-toggle-row">
      <div class="phase-toggle-info">
        <div class="phase-toggle-title">Send solver summary on upload</div>
        <div class="phase-toggle-sub">One consolidated email per solver, listing their pending jobs</div>
      </div>
      <label class="toggle">
        <input type="checkbox" ${checked} onchange="toggleSolverSummary(${phase}, this.checked)">
        <span class="slider"></span>
      </label>
    </div>`;
}

async function toggleSolverSummary(phase, enabled) {
  try {
    await API.updatePhaseSetting(phase, { solver_summary_enabled: enabled });
    const idx = _phaseSettings.findIndex(s => s.phase === phase);
    if (idx >= 0) _phaseSettings[idx].solver_summary_enabled = enabled;
    else _phaseSettings.push({ phase, solver_summary_enabled: enabled });
    showToast(`Solver summary ${enabled ? 'enabled' : 'disabled'} for ${PHASE_LABEL[phase] || 'phase'}`, 'info');
  } catch (e) {
    showToast('Failed: ' + e.message, 'error');
  }
}
window.toggleSolverSummary = toggleSolverSummary;

function renderRuleCard(rule) {
  const TIMING_OPTIONS = [
    { value: 'immediate',    label: 'Immediate (after delay)' },
    { value: 'same_day_5pm', label: 'Same day at 5:00 PM' },
    { value: 'next_day_9am', label: 'Next morning at 9:00 AM' },
    { value: 'next_day_8am', label: 'Next day at 8:00 AM' },
    { value: 'days',         label: 'After N days' },
  ];
  return `
    <div class="rule-card" id="rule-card-${rule.id}">
      <div class="rule-head">
        <span class="reason-badge ${REASON_CLASS[rule.reason_code] || ''}">${rule.reason}</span>
        <label class="toggle" style="margin-left:auto;">
          <input type="checkbox" ${rule.enabled ? 'checked' : ''}
            onchange="toggleRule('${rule.id}', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
      <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-top:14px;">
        <div>
          <label style="font-size:11px;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px;">Timing</label>
          <select id="rule-timing-${rule.id}" style="padding:7px 10px;border-radius:6px;border:1px solid var(--border-default);font-size:13px;background:var(--bg-card);color:var(--text-primary);">
            ${TIMING_OPTIONS.map(o => `<option value="${o.value}" ${rule.timing === o.value ? 'selected' : ''}>${o.label}</option>`).join('')}
          </select>
        </div>
        <div>
          <label style="font-size:11px;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px;">Delay mins</label>
          <input type="number" id="rule-delay-mins-${rule.id}" value="${rule.delay_minutes || 15}" min="0" max="1440"
            style="width:80px;padding:7px 10px;border-radius:6px;border:1px solid var(--border-default);font-size:13px;background:var(--bg-card);color:var(--text-primary);">
        </div>
        <div>
          <label style="font-size:11px;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px;">Delay days</label>
          <input type="number" id="rule-delay-days-${rule.id}" value="${rule.delay_days || 0}" min="0" max="30"
            style="width:80px;padding:7px 10px;border-radius:6px;border:1px solid var(--border-default);font-size:13px;background:var(--bg-card);color:var(--text-primary);">
        </div>
        <div>
          <label style="font-size:11px;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px;">Follow-up (days)</label>
          <input type="number" id="rule-followup-${rule.id}" value="${rule.followup_days || 3}" min="1" max="30"
            style="width:80px;padding:7px 10px;border-radius:6px;border:1px solid var(--border-default);font-size:13px;background:var(--bg-card);color:var(--text-primary);">
        </div>
        <button class="btn-primary" style="height:36px;align-self:flex-end;" onclick="saveRule('${rule.id}')">Save</button>
      </div>
    </div>`;
}

async function saveRule(ruleId) {
  const timing     = document.getElementById(`rule-timing-${ruleId}`).value;
  const delay_mins = parseInt(document.getElementById(`rule-delay-mins-${ruleId}`).value);
  const delay_days = parseInt(document.getElementById(`rule-delay-days-${ruleId}`).value);
  const followup   = parseInt(document.getElementById(`rule-followup-${ruleId}`).value) || 3;
  const enabled    = document.querySelector(`#rule-card-${ruleId} input[type=checkbox]`).checked;

  try {
    await API.updateRule(ruleId, {
      timing,
      delay_minutes: isNaN(delay_mins) ? 0 : delay_mins,
      delay_days:    isNaN(delay_days) ? 0 : delay_days,
      followup_days: followup,
      enabled
    });
    showToast(`Rule saved`, 'success');
  } catch(e) {
    showToast('Failed to save rule: ' + e.message, 'error');
  }
}

async function toggleRule(ruleId, enabled) {
  const timing     = document.getElementById(`rule-timing-${ruleId}`).value;
  const delay_mins = parseInt(document.getElementById(`rule-delay-mins-${ruleId}`).value);
  const delay_days = parseInt(document.getElementById(`rule-delay-days-${ruleId}`).value);
  const followup   = parseInt(document.getElementById(`rule-followup-${ruleId}`).value) || 3;
  try {
    await API.updateRule(ruleId, {
      timing,
      delay_minutes: isNaN(delay_mins) ? 0 : delay_mins,
      delay_days:    isNaN(delay_days) ? 0 : delay_days,
      followup_days: followup,
      enabled
    });
    showToast(`Rule ${enabled ? 'enabled' : 'disabled'}`, 'info');
  } catch(e) {
    showToast('Failed: ' + e.message, 'error');
  }
}
window.saveRule   = saveRule;
window.toggleRule = toggleRule;

/* =====================================================
   TEMPLATES EDITOR
   ===================================================== */

let _templates = [];

async function loadTemplates() {
  _templates = await API.getTemplates().catch(() => []);
  const tabsEl = document.getElementById('template-tabs');
  const editorEl = document.getElementById('templateEditor');
  if (!tabsEl || !editorEl) return;

  if (!_templates.length) {
    editorEl.innerHTML = '<div style="color:var(--text-tertiary);font-size:13px;padding:20px;">No templates found.</div>';
    return;
  }

  tabsEl.innerHTML = _templates.map((t, i) =>
    `<button class="template-btn ${i === 0 ? 'active' : ''}" onclick="selectTemplate('${t.id}', this)">${t.label}</button>`
  ).join('');

  renderTemplateEditor(_templates[0]);
}

function selectTemplate(id, btn) {
  document.querySelectorAll('.template-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const tmpl = _templates.find(t => t.id === id);
  if (tmpl) renderTemplateEditor(tmpl);
}
window.selectTemplate = selectTemplate;

function renderTemplateEditor(tmpl) {
  const el = document.getElementById('templateEditor');
  if (!el) return;
  el.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:14px;margin-top:16px;">
      <div>
        <label style="font-size:11px;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px;">Subject</label>
        <input type="text" id="tmpl-subject" value="${(tmpl.subject || '').replace(/"/g, '&quot;')}"
          style="width:100%;padding:10px 14px;border-radius:6px;border:1px solid var(--border-default);font-size:14px;background:var(--bg-card);color:var(--text-primary);box-sizing:border-box;">
      </div>
      <div>
        <label style="font-size:11px;color:var(--text-secondary);font-weight:600;display:block;margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px;">Body</label>
        <textarea id="tmpl-body" rows="12"
          style="width:100%;padding:10px 14px;border-radius:6px;border:1px solid var(--border-default);font-size:13px;font-family:var(--font-body);line-height:1.7;background:var(--bg-card);color:var(--text-primary);box-sizing:border-box;resize:vertical;">${tmpl.body || ''}</textarea>
      </div>
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        <button class="btn-primary" onclick="saveTemplate('${tmpl.id}')">Save template</button>
        <span style="font-size:12px;color:var(--text-tertiary);">
          Variables: <code>{{client_name}}</code> <code>{{vehicle_reg}}</code>
          <code>{{initiated_date}}</code> <code>{{scheduled_date}}</code>
          <code>{{solver_name}}</code> <code>{{solver_phone}}</code>
        </span>
      </div>
    </div>`;
}

async function saveTemplate(id) {
  const subject = document.getElementById('tmpl-subject').value.trim();
  const body    = document.getElementById('tmpl-body').value.trim();
  if (!subject || !body) { showToast('Subject and body cannot be empty', 'warning'); return; }
  try {
    await API.updateTemplate(id, { subject, body });
    const idx = _templates.findIndex(t => t.id === id);
    if (idx >= 0) { _templates[idx].subject = subject; _templates[idx].body = body; }
    showToast('Template saved', 'success');
  } catch(e) {
    showToast('Failed to save: ' + e.message, 'error');
  }
}
window.saveTemplate = saveTemplate;

/* =====================================================
   CONVERSION ANALYTICS
   ===================================================== */

let _conversionUploads = [];

async function loadConversion(baselineId = null, latestId = null) {
  const el = document.getElementById('conversion-content');
  if (!el) return;
  el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-tertiary);font-size:13px;">Loading conversion data…</div>';

  try {
    const [uploads, data] = await Promise.all([
      API.getConversionUploads().catch(() => []),
      API.getConversion(baselineId, latestId)
    ]);
    _conversionUploads = uploads || [];

    if (!data || !data.available) {
      el.innerHTML = `
        <div class="info-banner">${(data && data.message) || 'Upload at least two files to compute conversion.'}</div>
        <div class="panel"><div class="panel-header"><h3>Uploads so far</h3></div>
        <p style="color:var(--text-secondary);font-size:13px;">${_conversionUploads.length} upload(s) recorded.</p></div>`;
      return;
    }

    const r = data.rates, a = data.buckets.attributed, o = data.buckets.organic;

    el.innerHTML = `
      <div class="conversion-picker">
        <div>
          <label class="picker-label">Compare from (baseline)</label>
          <select id="conv-baseline">
            ${_conversionUploads.map(u => `<option value="${u.id}" ${u.id === data.baseline.id ? 'selected':''}>${convLabel(u)}</option>`).join('')}
          </select>
        </div>
        <div class="picker-arrow">→</div>
        <div>
          <label class="picker-label">To (latest)</label>
          <select id="conv-latest">
            ${_conversionUploads.map(u => `<option value="${u.id}" ${u.id === data.latest.id ? 'selected':''}>${convLabel(u)}</option>`).join('')}
          </select>
        </div>
        <button class="btn-secondary" id="conv-reset" style="height:38px;align-self:flex-end;">Reset to latest 2</button>
      </div>

      <div class="conversion-window">
        Window: <strong>${(data.baseline.uploaded_at||'').slice(0,16)}</strong> →
        <strong>${(data.latest.uploaded_at||'').slice(0,16)}</strong>
        · ${data.emails_in_window} email(s) sent in this window
      </div>

      <div class="kpi-grid kpi-grid-5">
        <div class="kpi-card" style="border-color:var(--accent);border-width:1.5px;">
          <p class="kpi-label">Overall attributed</p>
          <p class="kpi-value" style="color:var(--accent);">${r.attributed_overall_rate}%</p>
          <p class="kpi-sub">${a.any_forward} of ${a.total_emailed} emailed jobs moved forward</p>
        </div>
        <div class="kpi-card">
          <p class="kpi-label">Scheduling</p>
          <p class="kpi-value">${r.scheduling_rate}%</p>
          <p class="kpi-sub">${a.scheduling_conversion} of ${a.scheduling_eligible} initiated → scheduled+</p>
        </div>
        <div class="kpi-card">
          <p class="kpi-label">Inspection</p>
          <p class="kpi-value">${r.inspection_rate}%</p>
          <p class="kpi-sub">${a.inspection_conversion} of ${a.inspection_eligible} scheduled → inspected+</p>
        </div>
        <div class="kpi-card">
          <p class="kpi-label">Approval</p>
          <p class="kpi-value">${r.approval_rate}%</p>
          <p class="kpi-sub">${a.approval_conversion} of ${a.approval_eligible} inspected → approved${a.approval_cleared ? ` (${a.approval_cleared} cleared)` : ''}</p>
        </div>
        <div class="kpi-card">
          <p class="kpi-label">Organic</p>
          <p class="kpi-value">${r.organic_rate}%</p>
          <p class="kpi-sub">${o.any_forward} of ${o.total_not_emailed} non-emailed jobs moved</p>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header"><h3>Individual transitions</h3><span class="panel-meta">${data.transitions.length} shown</span></div>
        <div class="table-card" style="border:none;">
          <div class="table-head" style="grid-template-columns:1fr 1fr 1fr 1fr 1fr;">
            <div>Vehicle</div><div>Phase</div><div>From</div><div>To</div><div>Attribution</div>
          </div>
          <div class="table-body">
            ${data.transitions.length === 0
              ? '<div style="padding:40px;text-align:center;color:var(--text-tertiary);font-size:13px;">No forward movement in this window.</div>'
              : data.transitions.map(t => `
                <div class="table-row" style="grid-template-columns:1fr 1fr 1fr 1fr 1fr;cursor:default;">
                  <div class="cell-mono">${t.vehicle_reg}</div>
                  <div>${PHASE_LABEL[t.phase] || '—'}</div>
                  <div><span class="pipeline-pill pipeline-${(t.from||'').toLowerCase()}">${t.from}</span></div>
                  <div><span class="pipeline-pill pipeline-${(t.to||'').toLowerCase().split(' ')[0]}">${t.to}</span></div>
                  <div>${t.emailed ? '<span class="status-badge status-replied">Emailed</span>' : '<span class="status-badge status-awaiting">Organic</span>'}</div>
                </div>`).join('')}
          </div>
        </div>
      </div>`;

    const baseSel = document.getElementById('conv-baseline');
    const lateSel = document.getElementById('conv-latest');
    const onChange = () => {
      const b = parseInt(baseSel.value), l = parseInt(lateSel.value);
      if (b === l) { showToast('Baseline and latest must differ', 'warning'); return; }
      loadConversion(b, l);
    };
    baseSel.addEventListener('change', onChange);
    lateSel.addEventListener('change', onChange);
    document.getElementById('conv-reset').addEventListener('click', () => loadConversion(null, null));

  } catch (err) {
    el.innerHTML = `<div class="info-banner" style="background:var(--danger-soft);color:var(--danger-text);">Failed to load: ${err.message}</div>`;
  }
}

function convLabel(u) {
  const phase = u.detected_phase === 1 ? 'Sched' : u.detected_phase === 2 ? 'Insp' : u.detected_phase === 3 ? 'Approv' : '?';
  return `#${u.id} · ${(u.uploaded_at||'').slice(0,16)} · ${phase} · ${u.row_count} rows`;
}

/* =====================================================
   UPLOADS HISTORY
   ===================================================== */

async function loadUploads() {
  const el = document.getElementById('uploads-content');
  if (!el) return;
  el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-tertiary);font-size:13px;">Loading upload history…</div>';

  try {
    const uploads = await API.getUploadHistory().catch(() => []);
    if (!uploads || !uploads.length) {
      el.innerHTML = '<div class="info-banner">No uploads yet. Use the Upload button on the Pending jobs tab to import a Zoho export.</div>';
      return;
    }

    el.innerHTML = `
      <div class="info-banner">
        Click <strong>Set as baseline</strong> to fix an upload as the starting point for conversion analysis.
        If none is set, the system compares the two most recent uploads.
      </div>
      <div class="table-card">
        <div class="table-head" style="grid-template-columns:60px 150px 1.5fr 120px 70px 130px 90px 130px;">
          <div>#</div><div>Uploaded</div><div>Filename</div><div>Phase</div><div>Rows</div><div>Added / updated</div><div>Cleared</div><div>Baseline</div>
        </div>
        <div class="table-body">
          ${uploads.map(u => `
            <div class="table-row" style="grid-template-columns:60px 150px 1.5fr 120px 70px 130px 90px 130px;cursor:default;">
              <div class="cell-mono">#${u.id}</div>
              <div>${(u.uploaded_at||'').slice(0,16)}</div>
              <div title="${u.filename}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${u.filename}</div>
              <div><span class="phase-badge phase-${u.detected_phase}">${PHASE_LABEL[u.detected_phase] || '—'}</span></div>
              <div>${u.row_count}</div>
              <div class="cell-secondary">+${u.inserted} / ~${u.updated}</div>
              <div class="cell-secondary">${u.cleared || 0}</div>
              <div>${u.is_baseline
                ? '<span class="status-badge status-replied">Baseline</span>'
                : `<button class="btn-link" onclick="setBaseline(${u.id})">Set as baseline</button>`}</div>
            </div>`).join('')}
        </div>
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="info-banner" style="background:var(--danger-soft);color:var(--danger-text);">Failed to load: ${err.message}</div>`;
  }
}

async function setBaseline(id) {
  try {
    await API.setUploadBaseline(id);
    showToast('Baseline updated', 'success');
    loadUploads();
  } catch (err) {
    showToast('Failed: ' + err.message, 'error');
  }
}
window.setBaseline = setBaseline;

/* =====================================================
   SESSION BOOTSTRAP — keep users logged in across refreshes
   ===================================================== */
(async function restoreSession() {
  if (API.isLoggedIn && API.isLoggedIn()) {
    document.getElementById('login-view').style.display = 'none';
    document.getElementById('app').style.display = 'grid';
    const user = API.currentUser ? API.currentUser() : null;
    const nameEl = document.getElementById('user-name');
    if (nameEl && user) nameEl.textContent = user.name || user.email;
    await init();
  } else {
    showLoginView();
  }
})();
