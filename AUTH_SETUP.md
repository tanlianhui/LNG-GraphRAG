# User Login and History (MySQL)

Optional user registration and login with a **separate MySQL database**. When enabled, the app records **transcription edit history** and **query history** per user.

## Prerequisites

- **MySQL** via Docker (included in `docker-compose.yml`) or any MySQL 5.7+ / 8.x
- Python packages: `flask-login`, `pymysql` (see `requirements.txt`)

## MySQL via Docker

The project's **docker-compose.yml** includes a MySQL service for the auth database. Start it with Neo4j:

```bash
docker-compose up -d
```

This starts:
- **Neo4j** on 7474 (HTTP) and 7687 (Bolt)
- **MySQL** on 3306 with:
  - Database: `lng_graphrag_auth`
  - User: `lng_user` / Password: `lng-graphrag-password`
  - Root password: `lng-root-password` (for admin only)

Start only MySQL:

```bash
docker-compose up -d mysql
```

### MySQL admin UI (Adminer)

To **browse and edit the MySQL database** in your browser, start the **Adminer** service (included in `docker-compose.yml`):

```bash
docker-compose up -d adminer
```

Then open **http://localhost:8080**. Log in with:

| Field    | Value                |
|----------|----------------------|
| System   | **MySQL**            |
| Server   | **mysql**            |
| Username | **lng_user**         |
| Password | **lng-graphrag-password** |
| Database | **lng_graphrag_auth** |

(To use the root account instead: Username **root**, Password **lng-root-password**; leave Database empty to see all databases.)

### Fix: "Access denied for user 'lng_user'@'...'"

If Adminer or the web app gets **Access denied** when connecting as `lng_user`, MySQL may have created that user only for `localhost`. Allow connections from any host with this **one-time** command (run with MySQL already running):

```bash
docker exec -it lng-mysql mysql -u root -plng-root-password -e "
CREATE USER IF NOT EXISTS 'lng_user'@'%' IDENTIFIED BY 'lng-graphrag-password';
GRANT ALL PRIVILEGES ON lng_graphrag_auth.* TO 'lng_user'@'%';
FLUSH PRIVILEGES;
"
```

Then try logging in to Adminer again (Server: **mysql**, Username: **lng_user**, Password: **lng-graphrag-password**, Database: **lng_graphrag_auth**).

## Environment Variables

**No `.env` required for local Docker use.** The app’s defaults match `docker-compose.yml` (localhost, `lng_user`, `lng-graphrag-password`). Start MySQL with `docker-compose up -d mysql`, then run `python launch_web.py` — the webpage will connect to the Docker MySQL database without any env file. A Flask secret key is not required for local dev; the app uses a default.

To override (e.g. different host or password), add to `.env`:

```bash
# MySQL (only if different from docker-compose defaults)
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=lng_user
MYSQL_PASSWORD=lng-graphrag-password
MYSQL_DATABASE=lng_graphrag_auth

# Production only: set a strong secret for session cookies
# FLASK_SECRET_KEY=your-secret-key-here
```

If MySQL is not available or not configured, the app runs **without** login: no registration, no history; the dashboard works as before and the header shows "Login | Register" (login/register pages return 503 if MySQL is not configured).

## Tables

Start the web app after MySQL is running. On first request, the app creates the database (if missing) and tables: `users`, `edit_history`, `query_history`, `password_reset_tokens`. No manual SQL is required.

## Behaviour

- **Register**: `/register` → create account; user is logged in and redirected to dashboard.
- **Login**: `/login` → username or email + password; session cookie set.
- **Forgot password**: `/forgot-password` → enter email; a reset link is created (valid ~1 hour). If email sending is not configured, the link is shown on the page so the user can copy it.
- **Reset password**: `/reset-password?token=...` → set new password; token is single-use and expires after use or after ~1 hour.
- **Logout**: Dashboard header "Logout" → POST `/api/auth/logout`.
- **History**: When logged in, a **History** tab appears. It shows:
  - **Edit history**: document name, chunk id, timestamp, new text preview (from transcription chunk edits).
  - **Query history**: type (nl/cypher), timestamp, query preview, result count (from natural-language and Cypher queries).

Edits and queries are recorded **only when the user is logged in**. Anonymous users can still use the dashboard; they just have no history.

## API

- `POST /api/auth/register` — body: `{ "username", "email", "password" }`
- `POST /api/auth/login` — body: `{ "username" or "email", "password" }`
- `POST /api/auth/logout`
- `POST /api/auth/forgot-password` — body: `{ "email" }`; returns `{ "success", "message", "reset_link" }` (reset_link shown when email not configured)
- `POST /api/auth/reset-password` — body: `{ "token", "new_password" }`; token from reset link
- `GET /api/auth/me` — current user or `null`
- `GET /api/history/edits?limit=100` — edit history (login required)
- `GET /api/history/queries?limit=100` — query history (login required)

## Docker Compose

MySQL is defined in the project's **docker-compose.yml** as the `mysql` service (see "MySQL via Docker" above). Use `MYSQL_HOST=localhost` when the web app runs on the host; if the app runs inside Docker in the same Compose stack, use `MYSQL_HOST=mysql`.

## Troubleshooting

### `Access denied for user 'lng_user'@'192.168.65.1' (using password: YES)`

This happens when the web app runs on your **host** and connects to MySQL in Docker. MySQL sees the client as `192.168.65.1` (Docker’s gateway). The message means either:

1. **Wrong or missing password** — Your `.env` must set `MYSQL_PASSWORD` to the same value as in `docker-compose.yml`:
   ```bash
   MYSQL_PASSWORD=lng-graphrag-password
   ```
   If `MYSQL_PASSWORD` is missing or different, MySQL will reject the connection.

2. **User not allowed from that host** — The MySQL image creates `lng_user` with host `%` (any host). If you created the user manually and limited it to `localhost`, add a user or grant for `%` or `192.168.65.1`, or reuse the Docker defaults.

**Fix:** Ensure your `.env` contains (and that you restarted the web app after changing it):

```bash
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=lng_user
MYSQL_PASSWORD=lng-graphrag-password
MYSQL_DATABASE=lng_graphrag_auth
```
