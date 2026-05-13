/* =====================================================
   Solvit Valuation Portal — API layer
   Real backend calls with JWT auth.
   ===================================================== */

const API = {
  baseUrl: '/api',
  _token: null,

  async login(email, password) {
    const res = await fetch(`${this.baseUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Invalid credentials');
    }
    const data = await res.json();
    this._token = data.token;
    return data.user;
  },

  logout() { this._token = null; },

  _headers() {
    return {
      'Content-Type': 'application/json',
      ...(this._token ? { 'Authorization': `Bearer ${this._token}` } : {})
    };
  },

  async _get(path) {
    const res = await fetch(`${this.baseUrl}${path}`, { headers: this._headers() });
    if (res.status === 401) { this._handleUnauth(); return null; }
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  },

  async _patch(path, body = {}) {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: 'PATCH',
      headers: this._headers(),
      body: JSON.stringify(body)
    });
    if (res.status === 401) { this._handleUnauth(); return null; }
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  },

  _handleUnauth() {
    this._token = null;
    window.showLoginView && window.showLoginView();
    window.showToast && window.showToast('Session expired — please sign in again', 'warning');
  },

  async getJobs()              { return this._get('/jobs'); },
  async getJob(id)             { return this._get(`/jobs/${id}`); },
  async getEmailHistory(jobId) { return this._get(`/jobs/${jobId}/emails`); },
  async resolveJob(jobId)      { return this._patch(`/jobs/${jobId}/resolve`); },
  async getKpis()              { return this._get('/dashboard/kpis'); },
  async getEmailVolumeChart()  { return this._get('/charts/email-volume?days=7'); },
  async getReasonChart()       { return this._get('/charts/reasons'); },
  async getActivity()          { return this._get('/activity'); },
  async getLiveFeed()          { return this._get('/feed/live'); },
  async getIntegrationStatus() { return this._get('/integrations/status'); },

  async triggerZohoSync() {
    const res = await fetch(`${this.baseUrl}/zoho/sync`, {
      method: 'POST', headers: this._headers()
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Sync failed'); }
    return res.json();
  },

  async uploadJobs(file) {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${this.baseUrl}/upload/jobs`, {
      method: 'POST',
      headers: this._token ? { 'Authorization': `Bearer ${this._token}` } : {},
      body: form
    });
    if (res.status === 401) { this._handleUnauth(); return null; }
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Upload failed'); }
    return res.json();
  },

  async downloadTemplate() {
    const res = await fetch(`${this.baseUrl}/upload/template`, { headers: this._headers() });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'jobs_template.csv'; a.click();
    URL.revokeObjectURL(url);
  }
};

const TEMPLATES = {
  phase1: {
    name: 'Phase 1 — AM Team scheduling',
    from: 'support@solvit.co.ke',
    subject: "Vehicle valuation for {{vehicle_reg}} — let's schedule",
    body: "Dear {{client_name}},\n\nWe received a request to value your vehicle ({{vehicle_reg}}) on {{initiated_date}}, and our team has been trying to reach you by phone to schedule the valuation.\n\nPlease reply to this email with a date and time that works for you, or call us on +254 700 000 000.\n\nKind regards,\nAM Team\nSolvit Ltd"
  },
  phase2: {
    name: 'Phase 2 — Solver confirmation',
    from: 'support@solvit.co.ke',
    subject: 'Confirming your valuation inspection on {{scheduled_date}} — {{vehicle_reg}}',
    body: "Dear {{client_name}},\n\nYour vehicle valuation for {{vehicle_reg}} is scheduled for {{scheduled_date}}.\n\n{{solver_name}} from our team will be conducting the inspection and has been trying to reach you to confirm.\n\nPlease reply or contact {{solver_name}} on {{solver_phone}}.\n\nKind regards,\n{{solver_name}}\nSolvit Ltd"
  },
  followup: {
    name: '3-day follow-up',
    from: 'support@solvit.co.ke',
    subject: 'Following up on your vehicle valuation — {{vehicle_reg}}',
    body: "Dear {{client_name}},\n\nWe sent you a note 3 days ago about the valuation of your vehicle ({{vehicle_reg}}) but haven't heard back.\n\nPlease reply or call us on +254 700 000 000.\n\nKind regards,\nAM Team\nSolvit Ltd"
  }
};
