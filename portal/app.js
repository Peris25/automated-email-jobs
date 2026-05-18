/* =====================================================
   Solvit Valuation Portal — application logic
   Wired to real backend API
   ===================================================== */

const REASON_LABELS = { not_picking: 'Not picking', unreachable: 'Unreachable', not_ready: 'Not ready' };
const REASON_CLASS  = { not_picking: 'reason-not-picking', unreachable: 'reason-unreachable', not_ready: 'reason-not-ready' };

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
    if (btn.dataset.view === 'settings') loadIntegrationStatus();
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
    renderTemplate('phase1');
    bindFilters();
    bindTemplateTabs();
    bindUpload();
    updateNavCount();

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
    const statusBadge = j.status === 'replied'
      ? '<span class="status-badge status-replied">Reply received</span>'
      : `<span class="status-badge status-awaiting">Awaiting · ${j.emails_sent} sent</span>`;

    const solverOrInitiated = j.solver_name
      ? `<div class="cell-secondary">Solver:</div><div>${j.solver_name}</div>`
      : `<div class="cell-secondary">Initiated:</div><div>${j.initiated_date || '—'}</div>`;

    const lastSent = j.last_email_sent_at ? j.last_email_sent_at.split('T')[0] || j.last_email_sent_at.split(' ')[0] : '—';
    const lastTime = j.last_email_sent_at ? (j.last_email_sent_at.split('T')[1] || j.last_email_sent_at.split(' ')[1] || '') : '';

    return `
      <div class="table-row" data-job-id="${j.id}">
        <div><div class="cell-primary">${j.vehicle_reg}</div><div class="cell-secondary cell-mono">${j.id}</div></div>
        <div><div class="cell-primary">${j.client_name}</div><div class="cell-secondary">${j.client_email}</div></div>
        <div><span class="phase-badge">Phase ${j.phase}</span></div>
        <div><span class="reason-badge ${REASON_CLASS[j.reason] || ''}">${REASON_LABELS[j.reason] || j.reason || '—'}</span></div>
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
      <dt>Phase</dt><dd>Phase ${job.phase} — ${job.phase === 1 ? 'Scheduling' : 'Inspection confirmation'}</dd>
      <dt>Reason</dt><dd><span class="reason-badge ${REASON_CLASS[job.reason] || ''}">${REASON_LABELS[job.reason] || job.reason || '—'}</span></dd>
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
      // Convert to EAT (+3)
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
        <div><span class="phase-badge">Phase ${a.phase || '—'}</span></div>
        <div><span class="status-badge status-${(a.status||'').toLowerCase()}">${a.status || '—'}</span></div>
      </div>`;
   }).join('');
   // Update email activity KPIs from real data
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
   TEMPLATES
   ===================================================== */

function renderTemplate(key) {
  const t = TEMPLATES[key];
  const hl = s => s.replace(/\{\{(\w+)\}\}/g, '<span class="var-token">{{$1}}</span>');
  const bodyHtml = hl(t.body).replace(/\n/g, '<br>');

  document.getElementById('templatePreview').innerHTML = `
    <dl class="template-meta">
      <dt>From</dt><dd class="cell-mono">${t.from}</dd>
      <dt>Subject</dt><dd>${hl(t.subject)}</dd>
    </dl>
    <div class="template-body">${bodyHtml}</div>
    <div class="template-vars">
      <strong>Variables (filled automatically):</strong>
      <code>{{client_name}}</code><code>{{vehicle_reg}}</code>
      <code>{{initiated_date}}</code><code>{{scheduled_date}}</code>
      <code>{{solver_name}}</code><code>{{solver_phone}}</code>
    </div>`;
}

function bindTemplateTabs() {
  document.querySelectorAll('.template-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.template-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderTemplate(btn.dataset.template);
    });
  });
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
        showToast(`Uploaded: ${result.inserted} new, ${result.updated} updated, ${result.skipped} skipped`, 'success');
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
