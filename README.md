# Expense Tracker

The frontend is React/Vite. A FastAPI backend handles authentication and API routing, and SQLite stores accounts, expenses, travelers, spending limits, and the notification inbox in a local database file. Passwords are Argon2-hashed; the browser keeps only a signed session token.

## Requirements

- Node.js 20 or newer
- Python 3.10 or newer
- No separate database server is required; SQLite is included with Python.

## Run locally

1. Install frontend packages: `npm install`
2. Create an isolated Python environment: `python -m venv .venv`
3. Activate it in PowerShell: `.venv\Scripts\Activate.ps1`
4. Install API packages: `python -m pip install -r requirements.txt`
5. Copy `.env.example` to `.env` (PowerShell: `Copy-Item .env.example .env`) and set `JWT_SECRET` to a random value with at least 32 characters. `DATABASE_PATH` defaults to `server/expense_tracker.db`.
6. Start the React frontend and FastAPI API: `npm run dev`
7. Open `http://localhost:5173` and register an account, or import the legacy account and expenses as described below. The API health endpoint is `http://localhost:8000/api/health`.

## Share on the same Wi-Fi/LAN

The Vite development server listens on your laptop's network interfaces. Find your laptop's IPv4 address with `ipconfig`, then share `http://<laptop-ip>:5173` with people on the same trusted Wi-Fi/LAN. Keep `npm run dev` running, and allow the Node.js app through Windows Firewall only on private networks if prompted. This address is not a public internet link.

FastAPI automatically creates and updates the SQLite tables at startup. The database file remains on disk between restarts; back it up regularly. The former PostgreSQL database is not automatically copied into SQLite. Export any existing PostgreSQL data before switching, or use the legacy JSON import described below.

## Spending limits

The regular and travel spending limits compare against the cumulative total of all saved expenses in their respective categories. They are not monthly limits.

## Email notifications

Adding an expense creates an in-app notification only; it does not send email. Add a traveler with their name and email on the Travel overview; submitting an existing traveler's name again updates their email. Click **Send email** beside a traveler's total to send that person an itemized list of all recorded travel expenses assigned to them, with the total. Sending requires SMTP configuration.

Configure SMTP in `.env` to send email:

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-smtp-username
SMTP_PASSWORD=your-smtp-password
MAIL_FROM=expenses@example.com
SMTP_USE_TLS=
SMTP_START_TLS=
```

The API selects implicit TLS automatically for port `465` and STARTTLS for other ports, including the common submission port `587`. Leave both TLS settings blank for automatic selection. For a nonstandard mail server, set either `SMTP_USE_TLS` or `SMTP_START_TLS` to `true` or `false`; explicitly enabling one mode disables the automatically selected alternative, while explicitly enabling both is rejected as an invalid configuration. Keep SMTP credentials out of source control. If SMTP is not configured, in-app notifications continue to work; pressing **Send email** displays a configuration error.

Expense history is never deleted by the date filters. The Expenses and Travel expenses pages initially show the last 20 calendar days, including today; change or clear the **From date** and **To date** filters to view a wider range.

## Import existing JSON data

The original `db.json` is retained as a one-time import source. It contains legacy account data, including plaintext passwords; do not use those credentials for a public deployment. Run `npm run migrate:json` to import users, expenses, and travel companions without modifying the source file. The importer hashes legacy passwords and tracks the source file hash in SQLite, so repeating the command for the same file will not duplicate records. Imported travelers have no email address; add their email in the Travel overview before sending them a summary.

## Verify the app

Run `npm run build` to check and compile the frontend, and `python -m compileall -q server scripts` to check Python syntax. The API and database must be running and configured in `.env` for end-to-end account and expense flows.

## Production

Set `DATABASE_PATH`, `JWT_SECRET`, and optional SMTP settings in the hosting environment, then run `npm install`, create and activate a Python virtual environment, install `requirements.txt`, `npm run build`, and `npm start`. FastAPI serves the compiled React app from `dist`. Persist and back up the SQLite database file; use a persistent volume for it in hosted environments.

## Run with Docker

Install Docker Desktop (or Docker Engine with the Compose plugin), copy `.env.example` to `.env`, and set `JWT_SECRET` to a random value with at least 32 characters. Add SMTP settings if you want email notifications. Start the application from the project folder:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Open `http://localhost:8000`. Docker Compose keeps SQLite data in the `expense-tracker-data` named volume across container restarts and rebuilds. Back up that volume regularly. Use `docker compose logs -f` to inspect logs and `docker compose down` to stop the app; avoid `docker compose down -v` unless you intend to permanently delete the database volume. Set additional configuration such as `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `MAIL_FROM` in `.env`; the API reads these values when the container starts.

Keep `.env` and real credentials private. The Docker build excludes environment files, local databases, virtual environments, `node_modules`, and the legacy `db.json` file.

## Publish and deploy with GitHub Container Registry

The GitHub Actions workflow at `.github/workflows/publish-container.yml` builds the Docker image on pushes and pull requests. It publishes images to `ghcr.io/svs1911/travelanddailyexpencetracker` on branch pushes using the branch name and commit SHA as tags; pushes to the repository's default branch also update `latest`. Pull requests build the image without publishing it. The workflow uses the built-in `GITHUB_TOKEN`; no registry password or other repository secret is needed to publish.

To deploy on your own Linux server, install Docker Engine and the Docker Compose plugin, check out this repository for its `docker-compose.yml`, and copy `.env.example` to `.env`. Set a private `JWT_SECRET` of at least 32 characters and any SMTP settings. Leave `CONTAINER_IMAGE` set to the `latest` image or change it to a published branch/SHA tag. The first published GHCR package may be private: either change its package visibility to public, or sign in on the server using a GitHub account/PAT with `read:packages` access:

```sh
echo "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
docker compose pull
docker compose up -d --no-build
```

For private packages, keep `GHCR_TOKEN` out of shell history and store it securely; a fine-grained or classic token must have permission to read the package. Configure your firewall/reverse proxy and HTTPS before exposing the app publicly. Persist and back up the Compose volume `expense-tracker-data`; do not run `docker compose down -v` unless deleting the database is intended. Check `docker compose logs -f` for startup or email configuration errors. Docker must be installed and running both on the GitHub Actions runner (managed by GitHub) and on the deployment server.
