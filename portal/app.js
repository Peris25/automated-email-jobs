/* =====================================================
   Valuation Communication Portal — application logic
   ===================================================== */

const REASON_LABELS = {
  not_picking: 'Not picking',
  unreachable: 'Unreachable',
  not_ready: 'Not ready'
};

const REASON_CLASS = {
  not_picking: 'reason-not-picking',
  unreachable: 'reason-unreachable',
  not_ready: 'reason-not-ready'
};

const STATE = {
  jobs: [],
  activity: [],
  feed: [],
  charts: {}
};

/* =====================================================
   LOGIN
   ===================================================== */

document.getElementById('login-form').addEventListener('submit', e => {
  e.preventDefault();
  document.getElementById('login-view').style.display = 'none';
  document.getElementById('app').style.display = 'grid';
  init();
});

document.getElementById('logout-btn').addEventListener('click', () => {
  document.getElementById('app').style.display = 'none';
  document.getElementById('login-view').style.display = 'flex';
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
  });
});

/* =====================================================
   INITIALIZATION
   ===================================================== */

async function init() {
  // Set current date in header
  const today = new Date();
  document.getElementById('current-date').textContent =
    today.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  // Load all data in parallel
  const [jobs, activity, feed] = await Promise.all([
    API.getJobs(),
    API.getActivity(),
    API.getLiveFeed()
  ]);

  STATE.jobs = jobs;
  STATE.activity = activity;
  STATE.feed = feed;

  renderFeed();
  renderJobs();
  renderActivity();
  renderTemplate('phase1');
  bindFilters();
  bindTemplateTabs();

  // Charts last (Chart.js needs a moment after script load)
  setTimeout(initCharts, 100);
}

/* =====================================================
   LIVE FEED
   ===================================================== */

function renderFeed() {
  const iconMap = {
    sent: { class: 'sent', label: '→' },
    reply: { class: 'reply', label: '↩' },
    resolved: { class: 'resolved', label: '✓' }
  };

  document.getElementById('liveFeed').innerHTML = STATE.feed.map(item => {
    const icon = iconMap[item.type];
    return `
      <div class="feed-item">
        <div class="feed-icon ${icon.class}">${icon.label}</div>
        <div class="feed-text">${item.text}</div>
        <div class="feed-time">${item.time}</div>
      </div>
    `;
  }).join('');
}

/* =====================================================
   JOBS LIST
   ===================================================== */

function renderJobs() {
  const search = document.getElementById('jobSearch').value.toLowerCase();
  const phase = document.getElementById('phaseFilter').value;
  const reason = document.getElementById('reasonFilter').value;
  const status = document.getElementById('statusFilter').value;

  const filtered = STATE.jobs.filter(j => {
    if (search) {
      const haystack = `${j.vehicle_reg} ${j.client_name} ${j.solver_name || ''}`.toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    if (phase !== 'all' && j.phase !== parseInt(phase)) return false;
    if (reason !== 'all' && j.reason !== reason) return false;
    if (status !== 'all' && j.status !== status) return false;
    return true;
  });

  if (filtered.length === 0) {
    document.getElementById('jobsList').innerHTML = `
      <div style="padding: 40px; text-align: center; color: var(--text-tertiary); font-size: 13px;">
        No jobs match your filters
      </div>
    `;
    return;
  }

  document.getElementById('jobsList').innerHTML = filtered.map(j => {
    const statusBadge = j.status === 'replied'
      ? '<span class="status-badge status-replied">Reply received</span>'
      : `<span class="status-badge status-awaiting">Awaiting · ${j.emails_sent} sent</span>`;

    const solverOrInitiated = j.solver_name
      ? `<div class="cell-secondary">Solver:</div><div>${j.solver_name}</div>`
      : `<div class="cell-secondary">Initiated:</div><div>${j.initiated_date}</div>`;

    return `
      <div class="table-row" data-job-id="${j.id}">
        <div>
          <div class="cell-primary">${j.vehicle_reg}</div>
          <div class="cell-secondary cell-mono">${j.id}</div>
        </div>
        <div>
          <div class="cell-primary">${j.client_name}</div>
          <div class="cell-secondary">${j.client_email}</div>
        </div>
        <div><span class="phase-badge">Phase ${j.phase}</span></div>
        <div><span class="reason-badge ${REASON_CLASS[j.reason]}">${REASON_LABELS[j.reason]}</span></div>
        <div>
          <div>${j.last_email_sent_at.split(' ')[0]}</div>
          <div class="cell-secondary">${j.last_email_sent_at.split(' ')[1]}</div>
        </div>
        <div>${solverOrInitiated}</div>
        <div>${statusBadge}</div>
      </div>
    `;
  }).join('');

  // Bind row click handlers
  document.querySelectorAll('.table-row[data-job-id]').forEach(row => {
    row.addEventListener('click', () => openJobDetail(row.dataset.jobId));
  });
}

function bindFilters() {
  document.getElementById('jobSearch').addEventListener('input', renderJobs);
  document.getElementById('phaseFilter').addEventListener('change', renderJobs);
  document.getElementById('reasonFilter').addEventListener('change', renderJobs);
  document.getElementById('statusFilter').addEventListener('change', renderJobs);
}

/* =====================================================
   JOB DETAIL MODAL
   ===================================================== */

async function openJobDetail(jobId) {
  const job = STATE.jobs.find(j => j.id === jobId);
  if (!job) return;

  const history = await API.getEmailHistory(jobId);

  const content = `
    <div class="modal-header">
      <div>
        <h2>${job.vehicle_reg}</h2>
        <p style="color: var(--text-secondary); font-size: 13px; margin-top: 2px;">Job ${job.id}</p>
      </div>
      <button class="modal-close" id="modal-close">×</button>
    </div>

    <dl class="detail-grid">
      <dt>Client</dt><dd>${job.client_name}</dd>
      <dt>Email</dt><dd>${job.client_email}</dd>
      <dt>Phone</dt><dd>${job.client_phone}</dd>
      <dt>Phase</dt><dd>Phase ${job.phase} — ${job.phase === 1 ? 'Scheduling' : 'Inspection confirmation'}</dd>
      <dt>Reason</dt><dd><span class="reason-badge ${REASON_CLASS[job.reason]}">${REASON_LABELS[job.reason]}</span></dd>
      <dt>Initiated</dt><dd>${job.initiated_date}</dd>
      ${job.scheduled_date ? `<dt>Scheduled</dt><dd>${job.scheduled_date}</dd>` : ''}
      ${job.solver_name ? `<dt>Solver</dt><dd>${job.solver_name} · ${job.solver_phone}</dd>` : ''}
      <dt>Status</dt><dd>${job.status === 'replied' ? '<span class="status-badge status-replied">Reply received</span>' : '<span class="status-badge status-awaiting">Awaiting reply</span>'}</dd>
    </dl>

    <div class="detail-section">
      <h3>Email history</h3>
      <div class="email-history">
        ${history.map(h => `
          <div class="email-history-item">
            <div class="email-history-time">${h.sent_at} · ${h.type}</div>
            <div class="email-history-subject">${h.subject}</div>
            <div style="margin-top: 4px;"><span class="status-badge status-${h.status.toLowerCase()}">${h.status}</span></div>
          </div>
        `).join('')}
      </div>
    </div>
  `;

  document.getElementById('job-modal-content').innerHTML = content;
  document.getElementById('job-modal').style.display = 'flex';

  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.querySelector('.modal-overlay').addEventListener('click', closeModal);
}

function closeModal() {
  document.getElementById('job-modal').style.display = 'none';
}

/* =====================================================
   EMAIL ACTIVITY
   ===================================================== */

function renderActivity() {
  document.getElementById('activityList').innerHTML = STATE.activity.map(a => `
    <div class="table-row table-row-activity">
      <div>
        <div>${a.sent_at.split(' ')[0]}</div>
        <div class="cell-secondary">${a.sent_at.split(' ')[1]}</div>
      </div>
      <div class="cell-primary">${a.client}</div>
      <div class="cell-secondary cell-mono">${a.reg}</div>
      <div>${a.type}</div>
      <div><span class="phase-badge">Phase ${a.phase}</span></div>
      <div><span class="status-badge status-${a.status.toLowerCase()}">${a.status}</span></div>
    </div>
  `).join('');
}

/* =====================================================
   TEMPLATES
   ===================================================== */

function renderTemplate(key) {
  const t = TEMPLATES[key];
  // Highlight variable tokens with a span
  const highlighted = t.body.replace(/\{\{(\w+)\}\}/g, '<span class="var-token">{{$1}}</span>');
  const subjectHighlighted = t.subject.replace(/\{\{(\w+)\}\}/g, '<span class="var-token">{{$1}}</span>');

  document.getElementById('templatePreview').innerHTML = `
    <dl class="template-meta">
      <dt>From</dt><dd class="cell-mono">${t.from}</dd>
      <dt>Subject</dt><dd>${subjectHighlighted}</dd>
    </dl>
    <div class="template-body">${highlighted}</div>
    <div class="template-vars">
      <strong>Variables (filled from Zoho Analytics):</strong>
      <code>{{client_name}}</code>
      <code>{{vehicle_reg}}</code>
      <code>{{initiated_date}}</code>
      <code>{{scheduled_date}}</code>
      <code>{{solver_name}}</code>
      <code>{{solver_phone}}</code>
    </div>
  `;
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
   CHARTS
   ===================================================== */

async function initCharts() {
  const [volumeData, reasonData] = await Promise.all([
    API.getEmailVolumeChart(),
    API.getReasonChart()
  ]);

  // Volume chart
  const volumeCtx = document.getElementById('volumeChart').getContext('2d');
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
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.06)' }, ticks: { font: { size: 11 } } },
        x: { grid: { display: false }, ticks: { font: { size: 11 } } }
      },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, font: { size: 12 }, padding: 12 } }
      }
    }
  });

  // Reason donut chart
  const reasonCtx = document.getElementById('reasonChart').getContext('2d');
  STATE.charts.reason = new Chart(reasonCtx, {
    type: 'doughnut',
    data: {
      labels: reasonData.map(r => `${r.reason} (${r.count})`),
      datasets: [{
        data: reasonData.map(r => r.count),
        backgroundColor: ['#B07415', '#B83434', '#2E5FAE'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, font: { size: 12 }, padding: 10 } }
      }
    }
  });
}
