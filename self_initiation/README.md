# Self-Initiation Valuation Tool

Lets a client whose **insurer pays** for the valuation start the job themselves from the link in the
reminder SMS. It is a fork of the Private Valuation tool: the M-Pesa and pricing steps are gone, and
letter verification takes the place of "payment succeeded" as the thing that authorises the job.

This is a standalone Flask app and it does not share code or a database with the email portal in the
repository root.

## Client journey

1. SMS link opens `/self-initiate` (add `?src=sms-reminder` or similar to tag the campaign).
2. **Step 1:** upload the insurer's instruction letter and the logbook, then enter name and phone (email is optional).
3. The logbook is read only to pre-fill the plate. The letter is read for insurer name, date, reg and reference.
4. **Step 2:** confirm the reg and pick the insurer (pre-selected from the letter when possible).
   Location (Google Places search) and preferred time are optional.
5. Verification:
   - the insurer on the letter must match the selected insurer. Matching is tolerant: "APA Insurance Company Ltd" matches "APA", and each insurer can carry aliases.
   - the letter must be dated within `LETTER_MAX_AGE_DAYS` (90) days and not in the future
   - the exact same letter file must not have been used on an earlier request
6. If everything passes, the job is created in Solvit (`schedule-initiate-request`) with the selected insurer's company ID.
   If not, the request is **held** for review, never rejected outright. The client always sees a friendly
   "request received" page, and nothing is said to them about the check.

The reg on the letter is compared to the submitted reg and shown to reviewers. In v1 it does not block.

## Broker attribution

Jobs are created using the token of the account in `SOLVIT_USERNAME` / `SOLVIT_PASSWORD`, exactly like the
private tool. Set these to the **Self-Initiate broker alias** credentials and every job from this tool is
attributed to that broker. If Solvit turns out to need an explicit broker field in the payload instead,
it is one line in `services/solvit.py` (`build_payload`).

## Admin (`/admin`, password `ADMIN_PASSWORD`)

- **Requests:** tabs for held, initiated, send failed, rejected and abandoned drafts. Opening a request shows
  what was read off the letter, why it was held and both documents inline. Staff can correct the reg or
  insurer, then **Approve and create job in Solvit** (also the retry for failed sends) or **Reject**.
- **Insurers:** the list behind the client dropdown. Import a CSV with
  `name,solvit_company_id,aliases,active` (see `data/insurers_template.csv`). Rows are upserted by name, and
  each insurer can be edited or deactivated inline.

Documents are stored in the database rather than on disk, so they survive redeploys. The Solvit job comment
includes a link to the request's admin page, so the back office can open the proof from the job.

## Run locally

```bash
cd self_initiation
pip install -r requirements.txt
cp .env.example .env      # fill in OPENAI_API_KEY, SOLVIT_*, ADMIN_PASSWORD
flask --app app run       # http://localhost:5000/self-initiate
```

Tests (no network or API keys needed):

```bash
pip install pytest && python -m pytest tests
```

## Deploy

On Render, go to New, then Blueprint, and point it at `self_initiation/render.yaml`. That creates the web
service and its own Postgres database. Set the secret env vars in the dashboard, then embed
`https://<service>/self-initiate` on the website the same way as the private tool. `FRAME_ANCESTORS` can
restrict which sites may embed it.

## Still to confirm with the business

| Item | Where it plugs in |
|------|-------------------|
| Self-Initiate broker alias credentials | `SOLVIT_USERNAME`, `SOLVIT_PASSWORD` |
| Insurer list with Solvit company IDs | Admin, then Insurers, then Import CSV |
| Payment type for insurer-paid jobs (assumed `1`) | `SOLVIT_PAYMENT_TYPE` |
| Whether Solvit accepts document attachments | For now only a link goes in the job comment |
| Who owns the held-request queue | Admin access via `ADMIN_PASSWORD` |
