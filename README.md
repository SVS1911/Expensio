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

- Windows, macOS, or Linux.
- Node.js 20 or newer and npm.
- Python 3.10 or newer.
- Microsoft SQL Server 2019 or newer running locally or on a reachable private host.
- Microsoft ODBC Driver 18 for SQL Server on the machine running the Python API. On Linux, also install `unixODBC`/`unixODBC-dev`.

Install SQL Server Developer or Express edition for local development. Enable TCP/IP and SQL Server authentication (Mixed Mode), configure SQL Server to listen on port `1433`, and start the SQL Server service. Install the matching ODBC Driver 18 from Microsoft on the same machine that will run FastAPI. Do not expose a development SQL Server instance to the public internet.

## Run locally

Run all commands from the repository root.

### 1. Configure SQL Server

Start SQL Server and confirm that it accepts connections. The default example below assumes a SQL Server login named `sa` on `localhost,1433`. You can instead create a dedicated SQL login and use it in the connection string.

On first API startup, the configured SQL login must be permitted to create the application database. If you create the `ExpenseTracker` database yourself, grant the app login permission to create/alter the app tables and indexes.

### 2. Create and configure `.env`

In Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux:

```sh
cp .env.example .env
```

Open `.env` and replace the example `PWD` value in `SQLSERVER_CONNECTION_STRING` with your SQL Server password. Set `JWT_SECRET` to a private, random value at least 32 characters long. Keep `.env` private and never commit real passwords or secrets.

Example connection string for local SQL Server:

```text
Driver={ODBC Driver 18 for SQL Server};Server=localhost,1433;Database=ExpenseTracker;UID=sa;PWD=your-strong-password;Encrypt=yes;TrustServerCertificate=yes
```

Make sure the database named in `SQLSERVER_CONNECTION_STRING` matches `SQLSERVER_DATABASE`. The SQL login must be able to create that database on first startup or, if it already exists, create/alter the application schema.

### 3. Install frontend dependencies

Install the JavaScript packages from the lock file:

```sh
npm ci
```

### 4. Create and activate a Python environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, follow your organization's policy for local scripts or call the environment interpreter directly using `.\.venv\Scripts\python.exe`.

macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

### 5. Install API dependencies

With the virtual environment active:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 6. Start the frontend and API

Start both development servers together:

```sh
npm run dev
```

Open [http://localhost:5173](http://localhost:5173), then register an account. The frontend is served by Vite; the API runs at [http://localhost:8000](http://localhost:8000). FastAPI creates the configured SQL Server database (if it does not exist) and application tables on startup.

Check the API/database connection at [http://localhost:8000/api/health](http://localhost:8000/api/health). Keep the terminal open while using the app. Press `Ctrl+C` to stop both development servers.

### Optional: run frontend and API separately

Use two terminals from the project root. Activate the Python virtual environment in the API terminal.

API terminal:

```sh
npm run dev:api
```

Frontend terminal:

```sh
npm run dev:client
```

Vite proxies API requests to `localhost:8000`. Set `VITE_API_URL` only if you host the frontend and API on separate origins; it is a frontend build-time setting.

## Commands at a glance

| Purpose | Command |
| --- | --- |
| Install frontend dependencies | `npm ci` |
| Create Python virtual environment (Windows) | `python -m venv .venv` |
| Activate Python environment (Windows PowerShell) | `.\.venv\Scripts\Activate.ps1` |
| Create Python virtual environment (macOS/Linux) | `python3 -m venv .venv` |
| Activate Python environment (macOS/Linux) | `source .venv/bin/activate` |
| Install API dependencies | `python -m pip install -r requirements.txt` |
| Run frontend and API | `npm run dev` |
| Run only the API | `npm run dev:api` |
| Run only the frontend | `npm run dev:client` |
| Build frontend for production | `npm run build` |
| Check Python syntax | `python -m compileall -q server scripts tests` |
| Run API adapter tests | `python -m unittest discover -s tests -v` |
| Import legacy JSON data | `npm run migrate:json` |
| Copy previous SQLite data into SQL Server | `npm run migrate:sqlite` |
| Run the built app/API | `npm start` |

The development server serves the frontend at `http://localhost:5173`; the API health check is at `http://localhost:8000/api/health`.

## SQL Server settings

The API reads the following settings from `.env`:

| Variable | Purpose |
| --- | --- |
| `SQLSERVER_CONNECTION_STRING` | ODBC connection string used by the API. |
| `SQLSERVER_DATABASE` | Database created and used by the app; defaults to `ExpenseTracker`. |
| `JWT_SECRET` | Private token-signing secret; required and at least 32 characters. |
| `CORS_ORIGINS` | Comma-separated allowed browser origins; defaults to `http://localhost:5173`. |

For production, use a SQL Server certificate trusted by the API machine and enable certificate validation in the connection string rather than using `TrustServerCertificate=yes`. Use a least-privilege app login and keep database connectivity on a private network.

## Existing data migration

Back up both the source and destination databases before migration. Neither migration script deletes or edits its source data.

### Import legacy `db.json`

If the repository contains a legacy `db.json` export, configure `.env` and SQL Server first, then run:

```sh
npm run migrate:json
```

This imports accounts, expenses, and travelers, hashes legacy passwords, and records the source-file hash in SQL Server to avoid repeating the same import. The JSON file remains unchanged. It may contain plaintext passwords; protect it and do not reuse those passwords for a public deployment. Update imported travelers' email addresses in the Travel page before sending summaries.

### Migrate a previous SQLite database

Stop the old application and make a backup copy of the SQLite database first. Configure `.env` to connect to SQL Server, then run:

```sh
npm run migrate:sqlite
```

The default SQLite source is `server/expense_tracker.db`. To choose another source file, set `LEGACY_SQLITE_PATH` in the environment before running the command. The script copies users, travelers, settings, expenses, and notifications, leaves the SQLite source intact, and skips rows already present in SQL Server. Review the printed counts and verify the imported accounts and expenses before removing or retiring the old database.

## Using the app

1. Register or sign in.
2. Add regular expenses on **Expenses** or travel expenses on **Travel**. A travel expense must be assigned to a saved companion.
3. Add a travel companion's name and email and optionally a PNG, JPEG, or WebP photo no larger than 5 MB. Adding someone with an existing name updates that companion's email; a newly selected photo replaces their current photo.
4. Select a companion or their row in **Spend by person** to open their contact and assigned expense details. Close the dialog with its close button, by clicking outside, or with `Esc`.
5. Use the theme buttons in the lower-right corner to choose one of four palettes. The preference is saved in the current browser.
6. Set regular and travel spending limits on their overview pages. Limits apply to the cumulative total of saved expenses, not to an individual month.
7. Edit your account on **Profile**. Deleting your profile requires confirmation and permanently removes that user's expenses, companions, spending limits, and notifications.

Expense date filters only control which expenses are shown; they never delete expense history. Expense pages initially show the last 20 calendar days including today. Change or clear the date range to view older records.

## Email summaries

In-app notifications work without SMTP. To send an itemized travel expense summary to a companion, fill in these values in `.env`, then restart the API:

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-smtp-username
SMTP_PASSWORD=your-smtp-password
MAIL_FROM=expenses@example.com
SMTP_USE_TLS=
SMTP_START_TLS=
```

The API automatically uses implicit TLS on port `465` and STARTTLS on other ports, including `587`. Leave both TLS override values blank for automatic selection. For a nonstandard mail server, set either `SMTP_USE_TLS` or `SMTP_START_TLS` to `true` or `false`; explicitly enabling both is invalid. If SMTP is missing or misconfigured, in-app notifications continue to work and the API reports an email configuration or delivery error.

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

The frontend build and adapter tests do not require a live SQL Server. For an end-to-end check, start SQL Server and the API, open `/api/health`, register a test account, and create and retrieve an expense.

## Production run on a local server

To run the built application without the development server:

1. Configure production `SQLSERVER_CONNECTION_STRING`, `SQLSERVER_DATABASE`, `JWT_SECRET`, and any SMTP settings in the host environment.
2. Install Node.js, Python, Microsoft ODBC Driver 18, and the Python dependencies as described above.
3. Build the frontend:

   ```sh
   npm ci
   npm run build
   ```

4. Start FastAPI from the repository root:

   ```sh
   npm start
   ```

5. Open the configured host and port (default `http://localhost:8000`). FastAPI serves the compiled frontend from `dist`.

Before exposing the app outside your machine, use HTTPS through a trusted reverse proxy, set `CORS_ORIGINS` to the app's origin, secure SQL Server with a trusted TLS certificate and least-privilege login, restrict database network access, and configure database backups. Do not expose a development server or SQL Server directly to the public internet.

## Troubleshooting

- **API cannot connect to SQL Server:** Check the SQL Server service, hostname/port, TCP/IP, SQL authentication, firewall, ODBC Driver 18 installation, and connection string.
- **Database creation is denied:** Create the database ahead of time and grant the app login permission to create/alter the application tables and indexes, or use a login permitted to create the database on first startup.
- **ODBC driver not found:** Install Microsoft ODBC Driver 18 for SQL Server on the host running FastAPI. Restart the API after installation.
- **The app is not reachable:** Confirm `npm run dev` is running and check `http://localhost:8000/api/health`.
- **Email summaries fail:** Confirm SMTP host, port, TLS mode, username/password, sender address, and outbound network access. Email is optional.
