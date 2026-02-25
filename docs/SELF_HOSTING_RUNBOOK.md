# Self-Hosting Runbook (Replicate + Verify)

This runbook is the repeatable checklist for setting up the project on a new machine and verifying security/auth features.

---

## 0) Scope

Covers:
- local MySQL + Neo4j startup
- web app startup
- free public tunnel
- admin allowlist + app-level OTP 2FA
- post-setup verification steps

---

## 1) One-time machine setup

1. Clone repo and create virtual env.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start infrastructure:
   ```bash
   docker-compose up -d mysql neo4j
   ```
4. Ensure app DB initializes by opening web app once after startup.

---

## 2) Environment configuration

Create `.env` in repo root:

```bash
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=lng_user
MYSQL_PASSWORD=lng-graphrag-password
MYSQL_DATABASE=lng_graphrag_auth

FLASK_SECRET_KEY=replace-with-strong-random-secret

# Admin identity allowlist (required for admin endpoints/page)
ADMIN_EMAILS=you@example.com
# ADMIN_USERNAMES=your_username
```

---

## 3) Start app locally

```bash
python launch_web.py
```

Open:
- `http://localhost:5000`

---

## 4) Free public URL (no domain): tunnel service

```bash
ngrok http 5000
```

You will get a temporary URL like:
- `https://xxxxx.ngrok-free.app`

Notes:
- URL changes when you restart tunnel.
- Good for demo/testing; not stable production routing.

---

## 5) Admin 2FA setup (pyotp)

1. Register/login with an account included in `ADMIN_EMAILS` (or `ADMIN_USERNAMES`).
2. Open:
   - `http://localhost:5000/admin/2fa`
3. Click `Create Secret`.
4. Add it to your authenticator app:
   - **Google Authenticator (manual):**
     1. Tap `+` -> `Enter a setup key`
     2. `Account name`: use your app/user label (for example `LNG GraphRAG (you@example.com)`)
     3. `Your key`: paste the `secret` value shown on `/admin/2fa`
     4. `Type of key`: `Time based`
   - **About `otpauth URI`:**
     - Google Authenticator usually does **not** take a pasted URI directly.
     - It uses QR scan or setup key input.
     - The `otpauth URI` is mainly for apps/tools that import OTP links directly, or for generating a QR code.
5. Enter current OTP 6-digit number and click `Enable 2FA`.
6. Logout and login again; OTP must be required for that admin account.

---

## 6) Verification checklist (copy/paste tests)

## A. Auth baseline

- Register:
  - `POST /api/auth/register` works
- Login (non-admin):
  - `POST /api/auth/login` works with username+password only
- `GET /api/auth/me` shows logged-in user

## B. Admin detection

- `GET /api/auth/me` for allowlisted admin returns:
  - `"is_admin": true`
- non-allowlisted account returns:
  - `"is_admin": false`

## C. Admin 2FA behavior

1. Before enabling 2FA:
   - admin login works without OTP
2. After enabling 2FA:
   - admin login without OTP returns error with `requires_otp: true`
   - admin login with wrong OTP fails
   - admin login with valid OTP succeeds
3. Disable 2FA:
   - requires valid current OTP to disable

## D. Admin endpoint protection

- `GET /api/admin/2fa/status`:
  - returns 401 if not logged in
  - returns 403 if logged in but not admin
  - returns 200 for logged-in admin

## 7) Port exposure safety checks

Current compose config binds these localhost-only:
- MySQL: `127.0.0.1:3306`
- Neo4j: `127.0.0.1:7474`, `127.0.0.1:7687`
- Adminer: `127.0.0.1:8080`

Verify:
```bash
docker-compose ps
```

Do not expose DB/admin ports publicly.

---

## 8) What’s next

Recommended next improvements:
1. Add recovery codes for admin 2FA.
2. Add login rate limiting (`flask-limiter`) for `/api/auth/login`.
3. Add audit log table for admin actions.
4. Add QR rendering in `/admin/2fa` for easier onboarding.
5. Add automated smoke tests for auth + admin 2FA flows.

---

## 9) Rollback / emergency

- Disable app-level admin 2FA:
  - login as admin with valid OTP, go to `/admin/2fa`, disable
  - or set `otp_enabled=0` in MySQL `admin_2fa` table for the user
