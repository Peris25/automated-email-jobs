# Solvit Valuation Communication Portal — Backend

Automated email system that follows up with clients on pending vehicle valuation jobs via **cs-team@solvit.co.ke**, with full reply tracking via Microsoft Graph.

## Architecture

```
CSV Upload / Zoho Analytics
          ↓
  FastAPI (Render Web Service)
          ↓
  PostgreSQL (Render DB)
          ↓
  Microsoft Graph API
          ↓
  cs-team@solvit.co.ke
```

## Quick start (local)

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — at minimum set MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET

# 3. Run
uvicorn main:app --reload --port 8000
# → API at http://localhost:8000
# → Docs at http://localhost:8000/docs
```

Local dev uses **SQLite** automatically (`solvit_dev.db` in the project folder).  
Connect pgAdmin to it via File → Add Server → SQLite (or use the Render connection string directly).

---

## Deploying to Render

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/YOUR_ORG/solvit-backend.git
git push -u origin main
```

### Step 2 — Create services on Render
1. Go to https://render.com → New → Blueprint
2. Connect your GitHub repo
3. Render reads `render.yaml` and creates:
   - **solvit-valuation-api** (Web Service — Python)
   - **solvit-db** (PostgreSQL)

### Step 3 — Set secret env vars in Render dashboard
Go to your Web Service → Environment → add:
- `MS_TENANT_ID`
- `MS_CLIENT_ID`
- `MS_CLIENT_SECRET`
- `ADMIN_PASSWORD` (your portal login password)

`DATABASE_URL` is auto-filled by Render from the linked database.

### Step 4 — Connect pgAdmin to Render DB (for local inspection)
1. Render dashboard → solvit-db → Info tab → copy **External Database URL**
2. pgAdmin → Add Server:
   - Host: the hostname from the URL
   - Port: 5432
   - Database, Username, Password: from the URL
   - SSL mode: require

---

## Microsoft Graph setup (one-time, ~20 minutes)

### Register the app
1. Go to https://entra.microsoft.com (sign in with your Microsoft 365 admin account)
2. **Azure Active Directory → App registrations → New registration**
   - Name: `Solvit Mailer`
   - Supported account types: *Accounts in this organizational directory only*
   - Click Register

### Add permissions
3. **API permissions → Add a permission → Microsoft Graph → Application permissions**
   Add all three:
   - `Mail.Send`
   - `Mail.Read`
   - `Mail.ReadBasic`
4. Click **Grant admin consent for [your org]** (requires Global Admin)

### Get credentials
5. **Overview** → copy:
   - **Application (client) ID** → `MS_CLIENT_ID`
   - **Directory (tenant) ID** → `MS_TENANT_ID`
6. **Certificates & secrets → New client secret**
   - Description: `Solvit Backend`
   - Expiry: 24 months
   - Click Add → **copy the Value immediately** → `MS_CLIENT_SECRET`
   ⚠️ You cannot see this value again after leaving the page.

### Verify the sender mailbox
Ensure `cs-team@solvit.co.ke` exists as a mailbox in your Microsoft 365 admin centre.  
The app does **not** need the mailbox password — it uses app-level permissions.

### SPF / DKIM / DMARC for solvit.co.ke
These go on your **solvit.co.ke** DNS (not valuationco.co.ke):
- Microsoft 365 admin → Settings → Domains → solvit.co.ke → DNS records
- Follow the guided setup there — it shows the exact TXT/CNAME records to add

---

## Zoho Analytics setup (when ready)

### Get OAuth credentials
1. Go to https://api-console.zoho.com → **Self Client**
2. Click **Generate Code**:
   - Scope: `ZohoAnalytics.data.read,ZohoAnalytics.metadata.read`
   - Time Duration: 10 minutes
   - Copy the **Grant Token** (valid for 10 min only)

### Exchange grant token for refresh token (one-time)
Run this in your terminal immediately after copying the grant token:
```bash
curl -X POST https://accounts.zoho.com/oauth/v2/token \
  -d "code=YOUR_GRANT_TOKEN" \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "redirect_uri=https://www.zoho.com/books" \
  -d "grant_type=authorization_code"
```
From the response, copy the `refresh_token` → `ZOHO_REFRESH_TOKEN`.  
The refresh token never expires (unless revoked).

### Find your Workspace ID and View ID
Open your Zoho Analytics pending jobs view. The URL looks like:
```
https://analytics.zoho.com/workspace/123456789/view/987654321
```
- `123456789` → `ZOHO_WORKSPACE_ID`
- `987654321` → `ZOHO_VIEW_ID`

### Column mapping
Edit `services/zoho.py` → `ZOHO_COLUMN_MAP` to match your exact Zoho column headers.

### Switch data source
In your Render env vars (or .env):
```
DATA_SOURCE=zoho
```
The backend will then sync from Zoho every 15 minutes automatically.

---

## Email templates

Templates are in `services/templates.py`. Each reason code × phase has its own function.  
Edit the HTML there to customise wording.

| Template key      | When sent |
|-------------------|-----------|
| `phase1_not_picking`  | Phase 1, client not answering phone |
| `phase1_unreachable`  | Phase 1, completely unreachable |
| `phase1_not_ready`    | Phase 1, client not ready |
| `phase2_not_picking`  | Phase 2, appointment unconfirmed |
| `phase2_unreachable`  | Phase 2, unreachable with appointment set |
| `phase2_not_ready`    | Phase 2, needs to reschedule |
| `followup`            | 3-day follow-up for any phase/reason |

---

## Timing rules

| Reason code   | First email sent |
|---------------|-----------------|
| `unreachable` | Within 15 minutes of being loaded |
| `not_picking` | At 5:00 PM EAT same day |
| `not_ready`   | At 9:00 AM EAT next day |
| Follow-up     | 3 days after first email, if no reply |
| Max emails    | 2 per job — then flagged for manual handling |

---

## API reference

Full interactive docs: `http://localhost:8000/docs` (Swagger UI)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | Get JWT token |
| GET | `/api/jobs` | List pending jobs |
| GET | `/api/jobs/{id}` | Job detail |
| GET | `/api/jobs/{id}/emails` | Email history for job |
| PATCH | `/api/jobs/{id}/resolve` | Manually resolve job |
| POST | `/api/upload/jobs` | Upload CSV/Excel |
| GET | `/api/upload/template` | Download CSV template |
| POST | `/api/zoho/sync` | Trigger manual Zoho sync |
| GET | `/api/zoho/status` | Zoho connection status |
| GET | `/api/activity` | Email audit log |
| GET | `/api/feed/live` | Live activity feed |
| GET | `/api/dashboard/kpis` | Dashboard metrics |
| GET | `/api/charts/email-volume` | 7-day volume chart |
| GET | `/api/charts/reasons` | Breakdown by reason |
| GET | `/api/integrations/status` | Graph + Zoho health |

---

## Switching the frontend to the real API

In the portal's `js/data.js`, change one flag:
```js
// Before (mock data):
USE_MOCK: true,

// After (real backend):
USE_MOCK: false,
baseUrl: 'https://solvit-valuation-api.onrender.com/api',
```

---

## CSV upload format

Download the template from `/api/upload/template` or use these headers:

| Column | Required | Example |
|--------|----------|---------|
| Job ID | No (auto-generated) | J-2841 |
| Vehicle Reg | Yes | KDA 421X |
| Client Name | Yes | James Mwangi |
| Client Email | Yes | james@example.com |
| Client Phone | No | +254712345678 |
| Phase | No (default 1) | 1 or 2 |
| Reason Code | No | not_picking / unreachable / not_ready |
| Initiated Date | No | 2026-05-01 |
| Scheduled Date | No | 2026-05-07 14:00 |
| Solver Name | No | David Kimani |
| Solver Phone | No | +254733444555 |
| Job Status | No (default pending) | pending |
| Reason Logged At | No | 2026-05-01 09:00 |

Column names are case-insensitive and flexible (e.g. "email", "Client Email", "client_email" all work).
