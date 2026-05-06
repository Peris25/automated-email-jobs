/* =====================================================
   Mock data — designed to mirror what your backend will return
   from Zoho Analytics. Each object below maps to a Zoho row.
   Replace this file's contents with API calls when going live.
   ===================================================== */

const MOCK_JOBS = [
  {
    id: 'J-2841',
    vehicle_reg: 'KDA 421X',
    client_name: 'James Mwangi',
    client_email: 'j.mwangi@email.com',
    client_phone: '+254 712 345 678',
    phase: 1,
    reason: 'not_picking',
    initiated_date: '2026-05-02',
    scheduled_date: null,
    solver_name: null,
    solver_phone: null,
    emails_sent: 1,
    last_email_sent_at: '2026-05-04 17:00',
    status: 'awaiting_reply',
    job_status: 'pending'
  },
  {
    id: 'J-2842',
    vehicle_reg: 'KCB 882M',
    client_name: 'Sarah Otieno',
    client_email: 's.otieno@email.com',
    client_phone: '+254 722 111 222',
    phase: 2,
    reason: 'unreachable',
    initiated_date: '2026-04-28',
    scheduled_date: '2026-05-06 10:00',
    solver_name: 'David Kimani',
    solver_phone: '+254 733 444 555',
    emails_sent: 2,
    last_email_sent_at: '2026-05-05 09:15',
    status: 'awaiting_reply',
    job_status: 'pending'
  },
  {
    id: 'J-2843',
    vehicle_reg: 'KDD 119P',
    client_name: 'Peter Kamau',
    client_email: 'p.kamau@email.com',
    client_phone: '+254 711 988 776',
    phase: 1,
    reason: 'not_ready',
    initiated_date: '2026-05-03',
    scheduled_date: null,
    solver_name: null,
    solver_phone: null,
    emails_sent: 1,
    last_email_sent_at: '2026-05-04 09:00',
    status: 'awaiting_reply',
    job_status: 'pending'
  },
  {
    id: 'J-2844',
    vehicle_reg: 'KCY 556T',
    client_name: 'Grace Wanjiru',
    client_email: 'g.wanjiru@email.com',
    client_phone: '+254 720 555 333',
    phase: 2,
    reason: 'not_picking',
    initiated_date: '2026-04-30',
    scheduled_date: '2026-05-07 14:00',
    solver_name: 'Mary Achieng',
    solver_phone: '+254 734 666 777',
    emails_sent: 1,
    last_email_sent_at: '2026-05-04 17:00',
    status: 'awaiting_reply',
    job_status: 'pending'
  },
  {
    id: 'J-2845',
    vehicle_reg: 'KDH 770R',
    client_name: 'Daniel Ochieng',
    client_email: 'd.ochieng@email.com',
    client_phone: '+254 715 222 111',
    phase: 1,
    reason: 'unreachable',
    initiated_date: '2026-05-04',
    scheduled_date: null,
    solver_name: null,
    solver_phone: null,
    emails_sent: 1,
    last_email_sent_at: '2026-05-05 08:45',
    status: 'awaiting_reply',
    job_status: 'pending'
  },
  {
    id: 'J-2846',
    vehicle_reg: 'KBZ 234Q',
    client_name: 'Lucy Njeri',
    client_email: 'l.njeri@email.com',
    client_phone: '+254 729 888 999',
    phase: 2,
    reason: 'not_ready',
    initiated_date: '2026-04-29',
    scheduled_date: '2026-05-08 11:00',
    solver_name: 'David Kimani',
    solver_phone: '+254 733 444 555',
    emails_sent: 1,
    last_email_sent_at: '2026-05-05 09:00',
    status: 'replied',
    job_status: 'pending'
  },
  {
    id: 'J-2847',
    vehicle_reg: 'KDF 901S',
    client_name: 'Michael Kiprotich',
    client_email: 'm.kiprotich@email.com',
    client_phone: '+254 718 333 444',
    phase: 1,
    reason: 'not_picking',
    initiated_date: '2026-05-01',
    scheduled_date: null,
    solver_name: null,
    solver_phone: null,
    emails_sent: 2,
    last_email_sent_at: '2026-05-05 17:00',
    status: 'awaiting_reply',
    job_status: 'pending'
  },
  {
    id: 'J-2848',
    vehicle_reg: 'KCT 445L',
    client_name: 'Anne Mutua',
    client_email: 'a.mutua@email.com',
    client_phone: '+254 725 777 666',
    phase: 2,
    reason: 'unreachable',
    initiated_date: '2026-04-27',
    scheduled_date: '2026-05-06 09:00',
    solver_name: 'John Mbugua',
    solver_phone: '+254 736 888 999',
    emails_sent: 2,
    last_email_sent_at: '2026-05-05 09:15',
    status: 'awaiting_reply',
    job_status: 'pending'
  },
  {
    id: 'J-2849',
    vehicle_reg: 'KCK 332B',
    client_name: 'Rose Atieno',
    client_email: 'r.atieno@email.com',
    client_phone: '+254 727 121 212',
    phase: 1,
    reason: 'not_picking',
    initiated_date: '2026-05-03',
    scheduled_date: null,
    solver_name: null,
    solver_phone: null,
    emails_sent: 1,
    last_email_sent_at: '2026-05-04 17:00',
    status: 'awaiting_reply',
    job_status: 'pending'
  },
  {
    id: 'J-2850',
    vehicle_reg: 'KDM 789N',
    client_name: 'Joseph Mutiso',
    client_email: 'j.mutiso@email.com',
    client_phone: '+254 731 909 808',
    phase: 2,
    reason: 'not_ready',
    initiated_date: '2026-04-30',
    scheduled_date: '2026-05-09 13:00',
    solver_name: 'Mary Achieng',
    solver_phone: '+254 734 666 777',
    emails_sent: 1,
    last_email_sent_at: '2026-05-05 09:00',
    status: 'awaiting_reply',
    job_status: 'pending'
  }
];

const MOCK_LIVE_FEED = [
  { time: '2 min ago', type: 'sent', text: 'Email sent to James Mwangi (KDA 421X) — phase 1 reminder' },
  { time: '5 min ago', type: 'reply', text: 'Reply received from Lucy Njeri (KBZ 234Q) — confirming inspection' },
  { time: '12 min ago', type: 'sent', text: 'Email sent to Daniel Ochieng (KDH 770R) — unreachable trigger' },
  { time: '18 min ago', type: 'resolved', text: 'Job J-2839 marked complete — client confirmed via reply' },
  { time: '24 min ago', type: 'sent', text: 'Follow-up email to Michael Kiprotich (KDF 901S) — 3-day re-check' },
  { time: '28 min ago', type: 'reply', text: 'Reply received from Anne Mutua — requesting reschedule' }
];

const MOCK_ACTIVITY = [
  { sent_at: '2026-05-05 17:00', client: 'Michael Kiprotich', reg: 'KDF 901S', type: 'Follow-up', phase: 1, status: 'Delivered' },
  { sent_at: '2026-05-05 09:15', client: 'Sarah Otieno',     reg: 'KCB 882M', type: 'Follow-up', phase: 2, status: 'Opened' },
  { sent_at: '2026-05-05 09:15', client: 'Anne Mutua',       reg: 'KCT 445L', type: 'Follow-up', phase: 2, status: 'Replied' },
  { sent_at: '2026-05-05 09:00', client: 'Lucy Njeri',       reg: 'KBZ 234Q', type: 'First send', phase: 2, status: 'Replied' },
  { sent_at: '2026-05-05 08:45', client: 'Daniel Ochieng',   reg: 'KDH 770R', type: 'First send', phase: 1, status: 'Delivered' },
  { sent_at: '2026-05-04 17:00', client: 'James Mwangi',     reg: 'KDA 421X', type: 'First send', phase: 1, status: 'Opened' },
  { sent_at: '2026-05-04 17:00', client: 'Grace Wanjiru',    reg: 'KCY 556T', type: 'First send', phase: 2, status: 'Delivered' },
  { sent_at: '2026-05-04 17:00', client: 'Rose Atieno',      reg: 'KCK 332B', type: 'First send', phase: 1, status: 'Delivered' },
  { sent_at: '2026-05-04 09:00', client: 'Peter Kamau',      reg: 'KDD 119P', type: 'First send', phase: 1, status: 'Delivered' },
  { sent_at: '2026-05-03 09:15', client: 'Sarah Otieno',     reg: 'KCB 882M', type: 'First send', phase: 2, status: 'Opened' },
  { sent_at: '2026-05-03 09:15', client: 'Anne Mutua',       reg: 'KCT 445L', type: 'First send', phase: 2, status: 'Delivered' },
  { sent_at: '2026-05-03 17:00', client: 'Joseph Mutiso',    reg: 'KDM 789N', type: 'First send', phase: 2, status: 'Bounced' }
];

const TEMPLATES = {
  phase1: {
    name: 'Phase 1 — AM Team scheduling',
    from: 'scheduling@valuationco.co.ke',
    subject: 'Vehicle valuation for {{vehicle_reg}} — let\'s schedule',
    body: `Dear {{client_name}},

We received a request to value your vehicle ({{vehicle_reg}}) on {{initiated_date}}, and our team has been trying to reach you by phone to schedule the valuation.

To move this forward, please reply to this email with a date and time that works for you, or call our scheduling team on +254 700 000 000.

The valuation typically takes 30 to 45 minutes and we will come to a location that suits you.

Kind regards,
AM Team
Valuation Company`
  },
  phase2: {
    name: 'Phase 2 — Solver confirmation',
    from: 'scheduling@valuationco.co.ke',
    subject: 'Confirming your valuation inspection on {{scheduled_date}} — {{vehicle_reg}}',
    body: `Dear {{client_name}},

Your vehicle valuation for {{vehicle_reg}} is scheduled for {{scheduled_date}}.

{{solver_name}} from our team will be conducting the inspection and has been trying to reach you to confirm.

Please reply to this email to confirm, or contact {{solver_name}} directly on {{solver_phone}}.

If you need to reschedule, please call our AM Team on +254 700 000 000.

Kind regards,
{{solver_name}}
Valuation Company`
  },
  followup: {
    name: '3-day follow-up',
    from: 'scheduling@valuationco.co.ke',
    subject: 'Following up on your vehicle valuation — {{vehicle_reg}}',
    body: `Dear {{client_name}},

We sent you a note 3 days ago about scheduling the valuation of your vehicle ({{vehicle_reg}}) but haven't heard back.

If you would still like to proceed, please reply to this email or call us on +254 700 000 000. If your circumstances have changed and you no longer need the valuation, please let us know so we can close the request.

Kind regards,
AM Team
Valuation Company`
  }
};

/* =====================================================
   API LAYER
   ===================================================== */
/* This object is the contract between the frontend and the
   backend. Right now each method returns mock data via a
   resolved Promise. When the backend is ready, replace each
   method body with a fetch() call to the real endpoint —
   the frontend will not need to change. */

const API = {
  baseUrl: '/api',  // change to your backend URL when ready

  async getJobs() {
    // PRODUCTION: return fetch(`${this.baseUrl}/jobs`).then(r => r.json());
    return Promise.resolve(MOCK_JOBS);
  },

  async getJob(id) {
    // PRODUCTION: return fetch(`${this.baseUrl}/jobs/${id}`).then(r => r.json());
    return Promise.resolve(MOCK_JOBS.find(j => j.id === id));
  },

  async getActivity() {
    // PRODUCTION: return fetch(`${this.baseUrl}/activity`).then(r => r.json());
    return Promise.resolve(MOCK_ACTIVITY);
  },

  async getLiveFeed() {
    // PRODUCTION: return fetch(`${this.baseUrl}/feed/live`).then(r => r.json());
    return Promise.resolve(MOCK_LIVE_FEED);
  },

  async getKpis() {
    // PRODUCTION: return fetch(`${this.baseUrl}/dashboard/kpis`).then(r => r.json());
    return Promise.resolve({
      pending_total: 47,
      pending_phase_1: 28,
      pending_phase_2: 19,
      emails_today: 34,
      emails_today_first: 12,
      emails_today_followup: 22,
      reply_rate_7d: 32,
      resolved_this_week: 23
    });
  },

  async getEmailVolumeChart() {
    // PRODUCTION: return fetch(`${this.baseUrl}/charts/email-volume?days=7`).then(r => r.json());
    return Promise.resolve({
      labels: ['Apr 29', 'Apr 30', 'May 1', 'May 2', 'May 3', 'May 4', 'May 5'],
      first_send: [18, 22, 15, 19, 14, 12, 12],
      followup:   [ 8, 10, 12, 14, 16, 18, 22]
    });
  },

  async getReasonChart() {
    // PRODUCTION: return fetch(`${this.baseUrl}/charts/reasons`).then(r => r.json());
    return Promise.resolve([
      { reason: 'Not picking',  count: 22 },
      { reason: 'Unreachable',  count: 15 },
      { reason: 'Not ready',    count: 10 }
    ]);
  },

  async getEmailHistory(jobId) {
    // PRODUCTION: return fetch(`${this.baseUrl}/jobs/${jobId}/emails`).then(r => r.json());
    return Promise.resolve([
      { sent_at: '2026-05-05 17:00', subject: 'Following up on your vehicle valuation', status: 'Delivered', type: 'Follow-up' },
      { sent_at: '2026-05-02 17:00', subject: 'Vehicle valuation — let us schedule',    status: 'Opened',    type: 'First send' }
    ]);
  }
};
