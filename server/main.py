import os
import re
import bcrypt
import sqlite3
from contextlib import contextmanager
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import jwt
from aiosmtplib import send as send_email
from aiosmtplib.errors import SMTPException
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, Field

load_dotenv()

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "server/expense_tracker.db"))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = Path(__file__).resolve().parents[1] / DATABASE_PATH
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
TOKEN_LIFETIME = timedelta(days=7)
CATEGORIES = {"Academic", "Food", "Travel", "Shopping", "Bills", "Entertainment", "Other"}
PASSWORD_HASHER = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="Expense Tracker API")

# Normalize configured origins and remove trailing slashes.
_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
_allowed_origins = []
for _origin in _raw_origins.split(","):
    _origin = _origin.strip().rstrip("/")
    if not _origin:
        continue
    if not _origin.startswith(("http://", "https://")):
        _origin = f"https://{_origin}"
    _allowed_origins.append(_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    messages = [error["msg"] for error in exc.errors()]
    return JSONResponse(status_code=422, content={"error": "; ".join(messages)})


@app.exception_handler(sqlite3.IntegrityError)
async def database_conflict(_request: Request, _exc: sqlite3.IntegrityError):
    return JSONResponse(status_code=409, content={"error": "That email address or record is already in use."})


class LoginInput(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class RegistrationInput(LoginInput):
    name: str = Field(min_length=1, max_length=100)


class ExpenseInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    amount: float = Field(gt=0, le=9999999999.99)
    category: str = Field(min_length=1, max_length=32)
    date: Date
    description: str = Field(default="", max_length=1000)
    expenseType: str = Field(default="regular", pattern="^(regular|travel)$")
    people: str | None = Field(default=None, max_length=100)


class ExpenseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    amount: float | None = Field(default=None, gt=0, le=9999999999.99)
    category: str | None = Field(default=None, min_length=1, max_length=32)
    date: Date | None = None
    description: str | None = Field(default=None, max_length=1000)
    expenseType: str | None = Field(default=None, pattern="^(regular|travel)$")
    people: str | None = Field(default=None, max_length=100)


class TravelerInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)


class SettingsInput(BaseModel):
    expenseLimit: float | None = Field(default=None, gt=0, le=9999999999.99)
    travelLimit: float | None = Field(default=None, gt=0, le=9999999999.99)


class ProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    emailNotifications: bool = True
    currentPassword: str | None = Field(default=None, max_length=128)
    newPassword: str | None = Field(default=None, min_length=8, max_length=128)


def amount_in_cents(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class DatabaseConnection(sqlite3.Connection):
    def execute(self, sql, parameters=(), /):
        normalized = tuple(
            str(value) if isinstance(value, UUID)
            else value.isoformat() if isinstance(value, (Date, datetime))
            else float(value) if isinstance(value, Decimal)
            else value
            for value in parameters
        )
        return super().execute(sql.replace("%s", "?"), normalized)


@contextmanager
def database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, factory=DatabaseConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_schema():
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                email_notifications INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_unique ON users (lower(email));
            CREATE TABLE IF NOT EXISTS expenses (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount > 0),
                category TEXT NOT NULL,
                expense_date TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                expense_type TEXT NOT NULL DEFAULT 'regular' CHECK (expense_type IN ('regular', 'travel')),
                people TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS expenses_user_date_idx ON expenses (user_id, expense_date DESC);
            CREATE TABLE IF NOT EXISTS travelers (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS travelers_user_name_unique ON travelers (user_id, lower(name));
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                expense_limit REAL,
                travel_limit REAL
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                email_status TEXT NOT NULL DEFAULT 'not_sent',
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS notifications_user_date_idx ON notifications (user_id, created_at DESC);
            """
        )
        traveler_columns = {row["name"] for row in connection.execute("PRAGMA table_info(travelers)")}
        if "email" not in traveler_columns:
            connection.execute("ALTER TABLE travelers ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
        if "email_notifications" not in user_columns:
            connection.execute("ALTER TABLE users ADD COLUMN email_notifications INTEGER NOT NULL DEFAULT 1")
        connection.execute("UPDATE notifications SET email_status = 'not_sent' WHERE email_status = 'pending'")


@app.on_event("startup")
def startup():
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET must be set to a random value with at least 32 characters.")
    create_schema()


def public_user(row):
    return {"id": str(row["id"]), "name": row["name"], "email": row["email"], "emailNotifications": bool(row["email_notifications"])}


def session_for(row):
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": str(row["id"]), "iat": now, "exp": now + TOKEN_LIFETIME}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"user": public_user(row), "token": token}


def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in to continue.")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please log in again.")
    with database() as connection:
        user = connection.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in to continue.")
    return user["id"]


UserId = Annotated[UUID, Depends(current_user)]


def expense_from_row(row):
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "amount": float(row["amount"]),
        "category": row["category"],
        "date": row["date"].isoformat() if isinstance(row["date"], Date) else row["date"],
        "description": row["description"],
        "expenseType": row["expense_type"],
        **({"people": row["people"]} if row["people"] else {}),
    }


def notification_from_row(row):
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "title": row["title"],
        "message": row["message"],
        "emailStatus": row["email_status"],
        "isRead": bool(row["is_read"]),
        "createdAt": row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else row["created_at"],
    }


def add_notification(connection, user_id, kind, title, message):
    row = connection.execute(
        """
        INSERT INTO notifications (id, user_id, kind, title, message, email_status)
        VALUES (%s, %s, %s, %s, %s, 'not_sent')
        RETURNING id
        """,
        (uuid4(), user_id, kind, title, message),
    ).fetchone()
    return row["id"]


async def send_email_message(recipient, subject, body):
    smtp_host = os.getenv("SMTP_HOST")
    mail_from = os.getenv("MAIL_FROM")
    if not smtp_host or not mail_from:
        raise HTTPException(503, "Email is not configured. Set SMTP_HOST and MAIL_FROM on the server.")
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as error:
        raise HTTPException(503, "SMTP_PORT must be a valid port number.") from error
    if not 1 <= smtp_port <= 65535:
        raise HTTPException(503, "SMTP_PORT must be between 1 and 65535.")

    def tls_override(name):
        value = os.getenv(name, "").strip().lower()
        if not value:
            return None
        if value not in {"true", "false"}:
            raise HTTPException(503, f"{name} must be true or false.")
        return value == "true"

    use_tls_override = tls_override("SMTP_USE_TLS")
    start_tls_override = tls_override("SMTP_START_TLS")
    if use_tls_override is True and start_tls_override is True:
        raise HTTPException(503, "Enable either SMTP_USE_TLS or SMTP_START_TLS, not both.")
    if use_tls_override is True:
        use_tls, start_tls = True, False
    elif start_tls_override is True:
        use_tls, start_tls = False, True
    else:
        use_tls = use_tls_override if use_tls_override is not None else smtp_port == 465
        start_tls = start_tls_override if start_tls_override is not None else smtp_port != 465

    message = EmailMessage()
    message["From"] = mail_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    try:
        await send_email(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=os.getenv("SMTP_USER") or None,
            password=os.getenv("SMTP_PASSWORD") or None,
            use_tls=use_tls,
            start_tls=start_tls,
            timeout=15,
        )
    except (OSError, SMTPException, ValueError) as error:
        print(f"Email delivery failed for {recipient}. Check the SMTP host, port, and credentials.")
        raise HTTPException(502, "Could not send the email. Check the SMTP configuration and try again.") from error


@app.get("/api/health")
def health():
    with database() as connection:
        connection.execute("SELECT 1")
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegistrationInput):
    name = payload.name.strip()
    email = payload.email.strip().lower()
    if not name:
        raise HTTPException(400, "Enter your name.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(400, "Enter a valid email address.")
    if len(payload.password) < 8:
        raise HTTPException(400, "Password must contain at least 8 characters.")
    try:
        with database() as connection:
            user = connection.execute(
                """
                INSERT INTO users (id, name, email, password_hash)
                VALUES (%s, %s, %s, %s)
                RETURNING id, name, email, email_notifications
                """,
                (uuid4(), name, email, PASSWORD_HASHER.hash(payload.password)),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        if "users.email" not in str(error) and "UNIQUE constraint failed" not in str(error):
            raise
        raise HTTPException(409, "Email already registered.")
    return session_for(user)


@app.post("/api/auth/login")
def login(payload: LoginInput):
    email = payload.email.strip().lower()
    with database() as connection:
        user = connection.execute(
            "SELECT id, name, email, email_notifications, password_hash FROM users WHERE lower(email) = %s",
            (email,),
        ).fetchone()
    if user is None:
        raise HTTPException(401, "Invalid email or password.")
    encoded_password = user["password_hash"]
    if encoded_password.startswith(("$2a$", "$2b$", "$2y$")):
        password_matches = bcrypt.checkpw(payload.password.encode()[:72], encoded_password.encode())
        if password_matches:
            with database() as connection:
                connection.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (PASSWORD_HASHER.hash(payload.password), user["id"]),
                )
    else:
        password_matches = PASSWORD_HASHER.verify(payload.password, encoded_password)
    if not password_matches:
        raise HTTPException(401, "Invalid email or password.")
    return session_for(user)


@app.get("/api/profile")
def get_profile(user_id: UserId):
    with database() as connection:
        row = connection.execute("SELECT id, name, email, email_notifications FROM users WHERE id = %s", (user_id,)).fetchone()
    return public_user(row)


@app.patch("/api/profile")
def update_profile(payload: ProfileInput, user_id: UserId):
    name = payload.name.strip()
    email = payload.email.strip().lower()
    if not name:
        raise HTTPException(400, "Enter your name.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(400, "Enter a valid email address.")
    with database() as connection:
        existing = connection.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,)).fetchone()
        if payload.newPassword:
            if not payload.currentPassword or not PASSWORD_HASHER.verify(payload.currentPassword, existing["password_hash"]):
                raise HTTPException(400, "Enter your current password to change it.")
            password_hash = PASSWORD_HASHER.hash(payload.newPassword)
            row = connection.execute(
                """
                UPDATE users SET name = %s, email = %s, email_notifications = %s, password_hash = %s
                WHERE id = %s RETURNING id, name, email, email_notifications
                """,
                (name, email, payload.emailNotifications, password_hash, user_id),
            ).fetchone()
        else:
            row = connection.execute(
                """
                UPDATE users SET name = %s, email = %s, email_notifications = %s
                WHERE id = %s RETURNING id, name, email, email_notifications
                """,
                (name, email, payload.emailNotifications, user_id),
            ).fetchone()
    return public_user(row)


@app.get("/api/expenses")
def get_expenses(user_id: UserId):
    with database() as connection:
        rows = connection.execute(
            """
            SELECT id, title, amount, category, expense_date AS date, description, expense_type, people
            FROM expenses WHERE user_id = %s ORDER BY expense_date DESC, created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [expense_from_row(row) for row in rows]


@app.post("/api/expenses", status_code=201)
def create_expense(payload: ExpenseInput, user_id: UserId):
    values = payload.model_dump()
    values["amount"] = amount_in_cents(values["amount"]) / 100
    if values["amount"] <= 0:
        raise HTTPException(400, "Amount must be at least ₹0.01.")
    values["title"] = values["title"].strip()
    values["description"] = values["description"].strip()
    if not values["title"]:
        raise HTTPException(400, "Enter an expense title.")
    if values["category"] not in CATEGORIES:
        raise HTTPException(400, "Select a valid expense category.")
    if values["date"] > Date.today():
        raise HTTPException(400, "Future dates are not allowed.")
    values["people"] = values["people"].strip() if values["people"] else None
    if values["expenseType"] == "travel" and not values["people"]:
        raise HTTPException(400, "Select a valid traveler.")

    with database() as connection:
        if values["expenseType"] == "travel":
            traveler = connection.execute(
                "SELECT 1 FROM travelers WHERE user_id = %s AND lower(name) = lower(%s)",
                (user_id, values["people"]),
            ).fetchone()
            if traveler is None:
                raise HTTPException(400, "Choose a traveler from your saved traveler list.")
        limit_row = connection.execute(
            "SELECT expense_limit, travel_limit FROM user_settings WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        limit_column = "travel_limit" if values["expenseType"] == "travel" else "expense_limit"
        limit = limit_row[limit_column] if limit_row else None
        before = connection.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = %s AND expense_type = %s",
            (user_id, values["expenseType"]),
        ).fetchone()["total"]
        if limit is not None and amount_in_cents(before) + amount_in_cents(values["amount"]) > amount_in_cents(limit):
            spending_type = "travel" if values["expenseType"] == "travel" else "regular"
            raise HTTPException(
                400,
                f"This expense would exceed your {spending_type} spending limit of ₹{limit:.2f}.",
            )
        row = connection.execute(
            """
            INSERT INTO expenses
              (id, user_id, title, amount, category, expense_date, description, expense_type, people)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, title, amount, category, expense_date AS date, description, expense_type, people
            """,
            (uuid4(), user_id, values["title"], values["amount"], values["category"], values["date"], values["description"], values["expenseType"], values["people"]),
        ).fetchone()
        detail = f"{values['title']} for ₹{values['amount']:.2f} was added."
        add_notification(connection, user_id, "expense_added", "Expense added", detail)
    return expense_from_row(row)


@app.patch("/api/expenses/{expense_id}")
def update_expense(expense_id: UUID, payload: ExpenseUpdate, user_id: UserId):
    changes = payload.model_dump(exclude_unset=True)
    with database() as connection:
        row = connection.execute(
            """
            SELECT id, title, amount, category, expense_date AS date, description, expense_type, people
            FROM expenses WHERE id = %s AND user_id = %s
            """,
            (expense_id, user_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Expense not found.")
        values = expense_from_row(row)
        values.update(changes)
        if any(values.get(field) is None for field in ("title", "amount", "category", "date", "expenseType")):
            raise HTTPException(400, "Expense title, amount, category, date, and type are required.")
        values["amount"] = amount_in_cents(values["amount"]) / 100
        if values["amount"] <= 0:
            raise HTTPException(400, "Amount must be at least ₹0.01.")
        values["title"] = values["title"].strip()
        values["description"] = (values.get("description") or "").strip()
        values["people"] = values.get("people", "").strip() or None
        if isinstance(values["date"], str):
            values["date"] = Date.fromisoformat(values["date"])
        if not values["title"] or values["category"] not in CATEGORIES:
            raise HTTPException(400, "Enter a valid expense title and category.")
        if values["date"] > Date.today():
            raise HTTPException(400, "Future dates are not allowed.")
        limit_row = connection.execute(
            "SELECT expense_limit, travel_limit FROM user_settings WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        limit_column = "travel_limit" if values["expenseType"] == "travel" else "expense_limit"
        limit = limit_row[limit_column] if limit_row else None
        other_total = connection.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = %s AND expense_type = %s AND id != %s",
            (user_id, values["expenseType"], expense_id),
        ).fetchone()["total"]
        if limit is not None and amount_in_cents(other_total) + amount_in_cents(values["amount"]) > amount_in_cents(limit):
            raise HTTPException(400, f"This change would exceed your spending limit of ₹{limit:.2f}.")
        if values["expenseType"] == "travel":
            if not values["people"]:
                raise HTTPException(400, "Select a valid traveler.")
            if connection.execute("SELECT 1 FROM travelers WHERE user_id = %s AND lower(name) = lower(%s)", (user_id, values["people"])).fetchone() is None:
                raise HTTPException(400, "Choose a traveler from your saved traveler list.")
        updated = connection.execute(
            """
            UPDATE expenses SET title = %s, amount = %s, category = %s, expense_date = %s,
                description = %s, expense_type = %s, people = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, title, amount, category, expense_date AS date, description, expense_type, people
            """,
            (values["title"], values["amount"], values["category"], values["date"], values["description"], values["expenseType"], values["people"], expense_id, user_id),
        ).fetchone()
    return expense_from_row(updated)


@app.delete("/api/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: UUID, user_id: UserId):
    with database() as connection:
        result = connection.execute("DELETE FROM expenses WHERE id = %s AND user_id = %s", (expense_id, user_id))
        if result.rowcount == 0:
            raise HTTPException(404, "Expense not found.")


@app.get("/api/travelers")
def get_travelers(user_id: UserId):
    with database() as connection:
        rows = connection.execute("SELECT id, name, email FROM travelers WHERE user_id = %s ORDER BY name", (user_id,)).fetchall()
    return [{"id": str(row["id"]), "name": row["name"], "email": row["email"]} for row in rows]


@app.post("/api/travelers", status_code=201)
def create_traveler(payload: TravelerInput, user_id: UserId):
    name = payload.name.strip()
    email = payload.email.strip().lower()
    if not name:
        raise HTTPException(400, "Enter a traveler name.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(400, "Enter a valid traveler email address.")
    try:
        with database() as connection:
            row = connection.execute(
                "SELECT id FROM travelers WHERE user_id = %s AND lower(name) = lower(%s)",
                (user_id, name),
            ).fetchone()
            if row:
                traveler_id = row["id"]
                row = connection.execute(
                    "UPDATE travelers SET email = %s WHERE id = %s RETURNING id, name, email",
                    (email, traveler_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "INSERT INTO travelers (id, user_id, name, email) VALUES (%s, %s, %s, %s) RETURNING id, name, email",
                    (uuid4(), user_id, name, email),
                ).fetchone()
    except sqlite3.IntegrityError as error:
        if "travelers.user_id" not in str(error) and "UNIQUE constraint failed" not in str(error):
            raise
        raise HTTPException(409, "That traveler is already on your list.")
    return {"id": str(row["id"]), "name": row["name"], "email": row["email"]}


@app.post("/api/travelers/{traveler_id}/send-summary")
async def send_traveler_summary(traveler_id: UUID, user_id: UserId):
    with database() as connection:
        traveler = connection.execute(
            "SELECT id, name, email FROM travelers WHERE id = %s AND user_id = %s",
            (traveler_id, user_id),
        ).fetchone()
        if traveler is None:
            raise HTTPException(404, "Traveler not found.")
        if not traveler["email"]:
            raise HTTPException(400, "Add an email address for this traveler first.")
        expenses = connection.execute(
            """
            SELECT title, amount, category, expense_date AS date, description
            FROM expenses
            WHERE user_id = %s AND expense_type = 'travel' AND lower(people) = lower(%s)
            ORDER BY expense_date, created_at
            """,
            (user_id, traveler["name"]),
        ).fetchall()
    if not expenses:
        raise HTTPException(400, "There are no travel expenses recorded for this person.")
    total_cents = sum(amount_in_cents(row["amount"]) for row in expenses)
    total = total_cents / 100
    details = "\n".join(
        f"- {row['date']}: {row['title']} | {row['category']} | ₹{float(row['amount']):.2f}"
        + (f" | {row['description']}" if row["description"] else "")
        for row in expenses
    )
    body = (
        f"Hello {traveler['name']},\n\n"
        f"Here is the complete travel expense summary recorded for you.\n\n"
        f"{details}\n\n"
        f"Total: ₹{total:.2f}\n"
        f"Number of expenses: {len(expenses)}\n"
    )
    await send_email_message(traveler["email"], f"Travel expense summary for {traveler['name']}", body)
    return {"sent": True, "recipient": traveler["email"], "total": total, "expenseCount": len(expenses)}


@app.delete("/api/travelers/{traveler_id}", status_code=204)
def delete_traveler(traveler_id: UUID, user_id: UserId):
    with database() as connection:
        result = connection.execute("DELETE FROM travelers WHERE id = %s AND user_id = %s", (traveler_id, user_id))
        if result.rowcount == 0:
            raise HTTPException(404, "Traveler not found.")


@app.get("/api/settings")
def get_settings(user_id: UserId):
    with database() as connection:
        row = connection.execute("SELECT expense_limit, travel_limit FROM user_settings WHERE user_id = %s", (user_id,)).fetchone()
    return {
        "expenseLimit": float(row["expense_limit"]) if row and row["expense_limit"] is not None else None,
        "travelLimit": float(row["travel_limit"]) if row and row["travel_limit"] is not None else None,
    }


@app.put("/api/settings")
def update_settings(payload: SettingsInput, user_id: UserId):
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "Provide at least one spending limit.")
    for key, value in values.items():
        if value is not None:
            values[key] = amount_in_cents(value) / 100
            if values[key] <= 0:
                raise HTTPException(400, "Spending limits must be at least ₹0.01.")
    with database() as connection:
        connection.execute(
            """
            INSERT INTO user_settings (user_id, expense_limit, travel_limit)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
              expense_limit = CASE WHEN %s THEN EXCLUDED.expense_limit ELSE user_settings.expense_limit END,
              travel_limit = CASE WHEN %s THEN EXCLUDED.travel_limit ELSE user_settings.travel_limit END
            """,
            (user_id, values.get("expenseLimit"), values.get("travelLimit"), "expenseLimit" in values, "travelLimit" in values),
        )
    return get_settings(user_id)


@app.get("/api/notifications")
def get_notifications(user_id: UserId):
    with database() as connection:
        rows = connection.execute(
            "SELECT id, kind, title, message, email_status, is_read, created_at FROM notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 100",
            (user_id,),
        ).fetchall()
        unread = connection.execute("SELECT count(*) AS total FROM notifications WHERE user_id = %s AND is_read = FALSE", (user_id,)).fetchone()["total"]
    return {"items": [notification_from_row(row) for row in rows], "unreadCount": unread}


@app.patch("/api/notifications/read-all")
def mark_all_notifications_read(user_id: UserId):
    with database() as connection:
        connection.execute("UPDATE notifications SET is_read = TRUE WHERE user_id = %s AND is_read = FALSE", (user_id,))
    return {"updated": True}


@app.patch("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: UUID, user_id: UserId):
    with database() as connection:
        result = connection.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s", (notification_id, user_id))
        if result.rowcount == 0:
            raise HTTPException(404, "Notification not found.")
    return {"updated": True}



frontend_directory = Path(__file__).resolve().parents[1] / "dist"
if frontend_directory.is_dir():
    app.mount("/", StaticFiles(directory=frontend_directory, html=True), name="frontend")
