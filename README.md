# Expense Tracker

Expense Tracker is a personal and travel expense web app. The React/Vite frontend talks to a FastAPI backend. Microsoft SQL Server stores accounts, expenses, travel companions, spending limits, and notifications. Passwords are Argon2-hashed; the browser stores a signed session token.

## Features

- Register and sign in; edit or permanently delete your profile.
- Create, search, filter, edit, and delete regular and travel expenses.
- Set cumulative spending limits for regular and travel expenses.
- Add travel companions with a name, email, and optional PNG, JPEG, or WebP photo (up to 5 MB).
- Select a companion to view their contact details and assigned expenses.
- Choose from four saved color themes.
- View in-app notifications and optionally email travel expense summaries.

## Requirements

For local development:

- Windows, macOS, or Linux.
- Node.js 20 or newer and npm.
- Python 3.10 or newer.
- Microsoft SQL Server 2019 or newer, with a SQL login that can create the app database on first run (or an already-created database with table permissions).
- Microsoft ODBC Driver 18 for SQL Server. On Linux, also install `unixODBC`/`unixODBC-dev`.

Docker Desktop (Windows/macOS) or Docker Engine with Docker Compose (Linux) can run both SQL Server and the app without a separately installed SQL Server.

## Quick start with Docker

This is the simplest way to run the complete app and SQL Server together.

1. Install and start Docker Desktop or Docker Engine with the Compose plugin.
2. From the repository root, copy the example environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

   On macOS or Linux, use `cp .env.example .env`.

3. Edit `.env` and set:
   - `SQLSERVER_PASSWORD` to a strong password that meets SQL Server's password policy.
   - `JWT_SECRET` to a private, random value of at least 32 characters.
   - Optionally configure the SMTP settings described under [Email summaries](#email-summaries).

   Keep `.env` private; never commit real passwords or secrets.

4. Build and start the app and database:

   ```sh
   docker compose up --build -d
   ```

   The first start downloads images and builds the app, so it may take a few minutes. Compose waits for SQL Server's health check before starting the API.

5. Open [http://localhost:8000](http://localhost:8000), register an account, and start recording expenses.
6. Confirm the API is healthy at [http://localhost:8000/api/health](http://localhost:8000/api/health). To view startup logs, run `docker compose logs -f`.
7. To stop the app while preserving data, run `docker compose down`. The SQL Server files remain in the `expense-tracker-sql-data` named volume. **Do not** run `docker compose down -v` unless you intend to delete that database volume.

## Local development

Use this setup when you want Vite's development server and automatic reload for frontend and API changes.

### 1. Install and start SQL Server

Install SQL Server 2019 or newer and enable SQL Server authentication (Mixed Mode). Start the SQL Server service and make sure it accepts TCP/IP connections. For a local SQL Server instance, the example connection string below expects it to listen on `localhost,1433`.

Install Microsoft's ODBC Driver 18 for SQL Server on the same machine that runs the Python API. On Linux, install `unixODBC`/`unixODBC-dev` as well. If you already have SQL Server on a different host or port, use those connection details in the next step.

Alternatively, run only the SQL Server service from this repository's Compose file:

```sh
docker compose up -d sqlserver
```

Set `SQLSERVER_PASSWORD` in `.env` before running that command. When the API runs directly on your computer, use `Server=localhost,1433` in its connection string.

### 2. Configure the environment

Copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```sh
cp .env.example .env
```

Set `SQLSERVER_PASSWORD` to a strong SQL Server password and set `JWT_SECRET` to a private random value of at least 32 characters. The sample `SQLSERVER_CONNECTION_STRING` uses SQL Server's `sa` login on `localhost,1433`; replace the server, database, username, and password values as appropriate for your installation.

The connection string must include a database name matching `SQLSERVER_DATABASE`. The API creates that database and its tables on startup, so the SQL login must have permission to create a database on first run. If you create the database yourself, grant the app login the permissions needed to create and modify tables and indexes.

Keep the SQL password in the connection string consistent with `SQLSERVER_PASSWORD`. The separate `SQLSERVER_PASSWORD` variable is required by the bundled Docker Compose SQL Server service; `SQLSERVER_CONNECTION_STRING` is used by the API.

### 3. Install dependencies

From the repository root, install frontend dependencies:

```sh
npm ci
```

Create and activate a Python virtual environment. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell prevents environment activation, either allow local scripts for your user according to your organization's policy or invoke the environment's Python directly as `.\.venv\Scripts\python.exe`.

On macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

Install the API packages:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Start the app

Start both the Vite frontend and FastAPI backend in one terminal:

```sh
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The API runs at [http://localhost:8000](http://localhost:8000) and its health endpoint is [http://localhost:8000/api/health](http://localhost:8000/api/health). Keep the terminal running while using the app. Press `Ctrl+C` to stop both development servers.

The first successful API startup creates the configured SQL Server database (if absent) and the application tables. Register a user from the app to begin.

### 5. Start services separately (optional)

For more control, run these from the repository root in separate terminals, with the Python virtual environment activated in the API terminal:

```sh
npm run dev:api
```

```sh
npm run dev:client
```

The Vite development server proxies API requests to `localhost:8000`. Set `VITE_API_URL` only when the frontend and API are hosted separately; it is a frontend build-time setting.

## SQL Server configuration

The API reads these settings from `.env` or its hosting environment:

| Variable | Purpose |
| --- | --- |
| `SQLSERVER_CONNECTION_STRING` | ODBC connection string used by the API. |
| `SQLSERVER_DATABASE` | Database name that the API creates and uses. Defaults to `ExpenseTracker`. |
| `SQLSERVER_PASSWORD` | Password for the bundled Compose SQL Server service. Keep it consistent with the connection string when using `sa`. |
| `JWT_SECRET` | Private signing secret; required and at least 32 characters. |
| `CORS_ORIGINS` | Comma-separated allowed browser origins; defaults to `http://localhost:5173`. |

For local SQL Server with ODBC Driver 18, a connection string has this form:

```text
Driver={ODBC Driver 18 for SQL Server};Server=localhost,1433;Database=ExpenseTracker;UID=sa;PWD=your-strong-password;Encrypt=yes;TrustServerCertificate=yes
```

Use a production certificate and appropriate TLS validation settings in production instead of trusting an unverified server certificate.

## Migrating existing data

The app does not automatically migrate data from an older database. Back up the source and destination databases before migration.

### Import legacy `db.json`

If the repository contains the old `db.json` export and SQL Server is configured, run:

```sh
npm run migrate:json
```

This imports accounts, expenses, and travel companions, hashes the legacy passwords, and records the source-file hash in SQL Server to avoid repeating the same import. It leaves the JSON file unchanged. Legacy JSON may contain plaintext passwords; protect the file, and do not reuse those passwords for public deployments. Imported companions may not have email addresses; update their details in the Travel page before sending a summary.

### Migrate a previous SQLite database

If you are upgrading an earlier SQLite-based installation, first stop the old app and make a backup copy of its database file. Configure SQL Server as above, then run:

```sh
npm run migrate:sqlite
```

By default, the script reads `server/expense_tracker.db`. To use another file, set `LEGACY_SQLITE_PATH` to its path before running the command. The script copies users, travelers, settings, expenses, and notifications, keeps the SQLite source unchanged, and skips rows already present in SQL Server so it can be re-run safely. Review the migration counts and verify the imported accounts and expenses before retiring the source database.

## Using the app

1. Register or sign in.
2. Add regular expenses on **Expenses** or travel expenses on **Travel**. A travel expense must be assigned to a saved companion.
3. On the Travel page, add a companion's name and email and optionally select a PNG, JPEG, or WebP photo no larger than 5 MB. Adding someone with an existing name updates that companion's email and photo when a new photo is provided.
4. Select a companion or their row in **Spend by person** to see their contact details and assigned travel expenses in a dialog. Close it with the close button, by clicking outside, or with `Esc`.
5. Use the theme buttons in the lower-right corner to choose a palette. The selection is saved in the current browser.
6. Set regular and travel spending limits on their overview pages. Limits apply to the cumulative total of saved expenses, not to a month.
7. Edit your account on **Profile**. Deleting your profile requires confirmation and permanently removes that user's expenses, companions, spending limits, and notifications.

Expense date filters only control which expenses are shown; they never delete expense history. Expense pages initially show the last 20 calendar days including today. Change or clear the date range to view older records.

## Email summaries

In-app notifications work without an SMTP server. To send a companion's itemized travel expense summary, configure these variables in `.env` before starting the API:

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-smtp-username
SMTP_PASSWORD=your-smtp-password
MAIL_FROM=expenses@example.com
SMTP_USE_TLS=
SMTP_START_TLS=
```

The API uses implicit TLS automatically on port `465` and STARTTLS on other ports, including `587`. Leave both TLS override values blank for automatic selection. For a nonstandard server, set either `SMTP_USE_TLS` or `SMTP_START_TLS` to `true` or `false`; explicitly enabling both is invalid. If SMTP is missing or misconfigured, in-app notifications continue to work and the API reports an email configuration/delivery error. Never commit real mail credentials.

## Build and verification

Run the frontend production build:

```sh
npm run build
```

Check Python syntax:

```sh
python -m compileall -q server scripts tests
```

Run the SQL query adapter tests:

```sh
python -m unittest discover -s tests -v
```

For an end-to-end check, start SQL Server and the API, then open `/api/health`, register a test account, and add and retrieve an expense. The frontend build and adapter tests do not require a live SQL Server.

## Production deployment

For a self-hosted deployment, use Docker Compose or deploy the built API container alongside a separately managed SQL Server instance.

Before exposing the app:

1. Set a unique, private `JWT_SECRET` (at least 32 characters) and strong SQL Server credentials in the hosting environment.
2. Use a production SQL Server connection string with TLS certificate validation enabled. Grant only the database permissions the app requires; database creation can be performed ahead of time by an administrator.
3. Persist SQL Server data on durable storage and configure regular database backups and restore testing.
4. Configure HTTPS at a reverse proxy or load balancer. Restrict database access to the application host; do not expose SQL Server publicly.
5. Configure `CORS_ORIGINS` for the deployed frontend origin and set SMTP settings only if email summaries are required.
6. Build the frontend with `npm run build`, install `requirements.txt`, and run `npm start`. FastAPI serves the built frontend from `dist`.

The included `.github/workflows/publish-container.yml` builds the Docker image on pushes and pull requests. Branch pushes publish to `ghcr.io/svs1911/travelanddailyexpencetracker` with branch and commit-SHA tags; pushes to the repository's default branch also update `latest`. Pull requests build without publishing. The workflow uses `GITHUB_TOKEN`.

To run the Compose deployment on a Linux server, install Docker Engine and its Compose plugin, copy `.env.example` to `.env`, set strong `SQLSERVER_PASSWORD` and `JWT_SECRET` values, configure optional SMTP, and then run:

```sh
docker compose up -d --no-build
```

This uses the configured `CONTAINER_IMAGE` (the example defaults to the `latest` GHCR image). If the image is private, authenticate to GHCR with a token that has `read:packages` permission before starting:

```sh
echo "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
docker compose pull
docker compose up -d --no-build
```

Keep the token out of shell history and store it securely. Persist and back up the `expense-tracker-sql-data` volume. Use `docker compose logs -f` to inspect startup issues. Do not run `docker compose down -v` unless you intend to permanently delete the database volume.

## Troubleshooting

- **API cannot connect to SQL Server:** Check the SQL Server service, hostname/port, TCP/IP, SQL authentication, firewall, ODBC Driver 18 installation, and the connection string. For Compose, the API connects to the `sqlserver` service; for a locally running API, use the host's address, usually `localhost,1433`.
- **Database creation is denied:** Create the database ahead of time and grant the configured login permission to create/alter the application tables and indexes, or use a login permitted to create the database on first startup.
- **ODBC driver not found:** Install Microsoft ODBC Driver 18 for SQL Server on the host running FastAPI. Rebuild the app image after changing the Dockerfile or Python dependencies.
- **Docker Compose reports a missing variable:** Set `SQLSERVER_PASSWORD` and `JWT_SECRET` in `.env`. SQL Server passwords must meet the SQL Server password policy.
- **The app is not reachable:** Check `docker compose ps` and `docker compose logs -f`; in local development, confirm both frontend and API terminals are running and test `/api/health`.
- **Email summaries fail:** Confirm SMTP host, port, TLS mode, username/password, sender address, and outbound network access. Email is optional.
