/* =====================================================
   Solvit Valuation Portal — API layer
   Real backend calls with JWT auth.
   ===================================================== */

const API = {
  baseUrl: '/api',
  _token: localStorage.getItem('solvit_token') || null,

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
    localStorage.setItem('solvit_token', data.token);
    localStorage.setItem('solvit_user', JSON.stringify(data.user));
    return data.user;
  },

  logout() {
    this._token = null;
    localStorage.removeItem('solvit_token');
    localStorage.removeItem('solvit_user');
  },

  currentUser() {
    try { return JSON.parse(localStorage.getItem('solvit_user') || 'null'); }
    catch { return null; }
  },

  isLoggedIn() { return !!this._token; },

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
    localStorage.removeItem('solvit_token');
    localStorage.removeItem('solvit_user');
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
  },

  // Rules
  async getRules() { return this._get('/rules'); },
  async updateRule(id, data) {
    const res = await fetch(`${this.baseUrl}/rules/${id}`, {
      method: 'PUT', headers: this._headers(), body: JSON.stringify(data)
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
    return res.json();
  },

  // Templates
  async getTemplates() { return this._get('/templates'); },
  async updateTemplate(id, data) {
    const res = await fetch(`${this.baseUrl}/templates/${id}`, {
      method: 'PUT', headers: this._headers(), body: JSON.stringify(data)
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
    return res.json();
  },

  // Upload history
  async getUploadHistory()    { return this._get('/upload/history'); },
  async setUploadBaseline(id) {
    const res = await fetch(`${this.baseUrl}/upload/${id}/baseline`, {
      method: 'PATCH', headers: this._headers()
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
    return res.json();
  },

  // Conversion analytics
  async getConversion(baselineId, latestId) {
    let path = '/conversion';
    const params = [];
    if (baselineId) params.push(`baseline=${baselineId}`);
    if (latestId)   params.push(`latest=${latestId}`);
    if (params.length) path += '?' + params.join('&');
    return this._get(path);
  },
  async getConversionUploads() { return this._get('/conversion/uploads'); },

  // Solvers directory
  async getSolvers()             { return this._get('/solvers'); },
  async addSolver(data) {
    const res = await fetch(`${this.baseUrl}/solvers`, {
      method: 'POST', headers: this._headers(), body: JSON.stringify(data)
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
    return res.json();
  },
  async updateSolver(id, data) {
    const res = await fetch(`${this.baseUrl}/solvers/${id}`, {
      method: 'PUT', headers: this._headers(), body: JSON.stringify(data)
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
    return res.json();
  },
  async deleteSolver(id) {
    const res = await fetch(`${this.baseUrl}/solvers/${id}`, {
      method: 'DELETE', headers: this._headers()
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
    return res.json();
  },

  // Phase settings
  async getPhaseSettings()       { return this._get('/phase-settings'); },
  async updatePhaseSetting(phase, data) {
    const res = await fetch(`${this.baseUrl}/phase-settings/${phase}`, {
      method: 'PUT', headers: this._headers(), body: JSON.stringify(data)
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
    return res.json();
  },

};
