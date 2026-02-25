# Self-Hosting on Your Own PC: Risks and Safer Setup

This guide explains what can go wrong when exposing your local LNG-GraphRAG service to the public, and how to reduce risk (including admin 2FA).

For step-by-step replication and testing, use **[SELF_HOSTING_RUNBOOK.md](SELF_HOSTING_RUNBOOK.md)**.

---

## Should you host on your own PC?

You can, but it is best for **personal use / small team / non-critical workloads**.

Main limitations:
- Your home/office internet can be unstable.
- Your PC reboots, sleeps, or disconnects.
- Residential IPs change.
- Security posture is usually weaker than a cloud VM.

If uptime and security are important, a cloud server is usually better.

---

## Risks of opening local ports to public internet

If you expose ports directly (router port-forward, public IP), risks include:

- **Automated scanning and attacks** within minutes (bots probing common ports and vulnerabilities).
- **Credential stuffing / brute force** on login endpoints.
- **Service exploit risk** (Flask, Neo4j, MySQL, reverse proxy vulnerabilities).
- **Data leakage** from weak auth/session config.
- **Ransomware/data loss** if host is compromised.
- **Lateral movement** to other devices on your LAN.

### High-risk ports you should NOT expose directly

- `3306` (MySQL)
- `7687` and `7474` (Neo4j Bolt/HTTP admin)
- Any admin/debug endpoints

Expose only one HTTPS entrypoint (or use an outbound tunnel).

---

## Tunnel vs direct port forwarding

### Direct port forwarding
- Pros: simple.
- Cons: highest exposure; your IP and open ports are visible to everyone.

### Tunnel service (recommended for home hosting)
- Pros:
  - No inbound router port forward required.
  - Origin can stay private.
  - Works with provider auth features if available.
- Cons:
  - You depend on tunnel provider availability.
  - Misconfigured Access policy can still expose app.

### Other options
- **Tailscale / ZeroTier**: safest for private access (VPN-only), not public web.
- **Ngrok / similar tunnels**: quick but check auth/rate-limit settings carefully.

---

## Recommended secure architecture (self-host)

1. Run app and DB locally:
   - Web app on `127.0.0.1:5000`
   - MySQL local-only
   - Neo4j local-only
2. Publish only through a secure edge:
   - Tunnel service (e.g., ngrok), or
   - Reverse proxy with HTTPS + strict auth
3. Keep DB/admin ports closed to internet.
4. Add 2FA for admin operations.

---

## Admin 2FA: how to do it locally

Use app-level TOTP via `pyotp` for admin users.

## App-level 2FA: TOTP inside Flask

Add 2FA directly in your app for admin users.

Implemented behavior in this repo:
1. Admin identity is controlled by env allowlist:
   - `ADMIN_EMAILS=a@b.com,c@d.com` and/or
   - `ADMIN_USERNAMES=alice,bob`
2. Admin OTP state is stored in MySQL table `admin_2fa` (`otp_secret`, `otp_enabled`).
3. Login requires OTP for admin users when `otp_enabled=1`.
4. Admin setup page is available at `/admin/2fa`:
   - Create secret
   - Enable/disable with current OTP
5. Admin APIs are protected by `@admin_required`.

Required Python lib:
- `pyotp`

---

## Minimum hardening checklist

- Use strong random passwords for MySQL and admin accounts.
- Set a strong `FLASK_SECRET_KEY`.
- Enable HTTPS only (TLS).
- Restrict by IP or identity provider where possible.
- Add rate limiting on login/admin routes.
- Keep OS, Docker images, Python deps updated.
- Run regular backups:
  - MySQL dumps
  - Neo4j backups
- Store secrets in env/secret manager, never in git.
- Monitor logs and failed login attempts.

---

## Practical recommendation

If you self-host on your PC and need remote access:

1. Use a **tunnel service** (not direct port forwarding).
2. Add **app-level admin 2FA** (TOTP).
3. Do not expose MySQL/Neo4j ports publicly.

This gives much better security while still keeping your current local deployment workflow.

