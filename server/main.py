import os
import re
import bcrypt
import base64
import pyodbc
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

SQLSERVER_CONNECTION_STRING = os.getenv("SQLSERVER_CONNECTION_STRING", "").strip()
SQLSERVER_DATABASE = os.getenv("SQLSERVER_DATABASE", "ExpenseTracker").strip()
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


@app.exception_handler(pyodbc.IntegrityError)
async def database_conflict(_request: Request, _exc: pyodbc.IntegrityError):
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
    image: str | None = Field(default=None, max_length=7_000_000)


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


class QueryResult:
    def __init__(self, cursor):
        self.cursor = cursor
        self.columns = [column[0] for column in cursor.description] if cursor.description else []
        self.rowcount = cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(zip(self.columns, row)) if row is not None else None

    def fetchall(self):
        return [dict(zip(self.columns, row)) for row in self.cursor.fetchall()]


class DatabaseConnection:
    def __init__(self, connection):
        self.connection = connection

    @staticmethod
    def _sql_server_sql(sql):
        returning = re.search(r"\s+RETURNING\s+(.+?)\s*;?\s*$", sql, re.IGNORECASE | re.DOTALL)
        if returning:
            output_columns = ", ".join(
                f"inserted.{column.strip().split(' AS ')[0].split(' as ')[0]}"
                + (f" AS {column.strip().split(' AS ', 1)[1]}" if " AS " in column else
                   f" AS {column.strip().split(' as ', 1)[1]}" if " as " in column else "")
                for column in returning.group(1).rstrip(";").split(",")
            )
            sql = sql[:returning.start()]
            if sql.lstrip().upper().startswith("INSERT"):
                sql = re.sub(r"\)\s*VALUES\b", f") OUTPUT {output_columns} VALUES", sql, count=1, flags=re.IGNORECASE)
            else:
                sql = re.sub(r"\s+WHERE\b", f" OUTPUT {output_columns} WHERE", sql, count=1, flags=re.IGNORECASE)
        sql = re.sub(
            r"\bSELECT\b(.*?)\bLIMIT\s+(\d+)\b",
            lambda match: f"SELECT TOP {match.group(2)}{match.group(1)}",
            sql,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        sql = re.sub(r"\bFALSE\b", "0", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bTRUE\b", "1", sql, flags=re.IGNORECASE)
        return sql.rstrip().replace("%s", "?")

    def execute(self, sql, parameters=()):
        cursor = self.connection.cursor()
        cursor.execute(self._sql_server_sql(sql), tuple(
            str(value) if isinstance(value, UUID)
            else value.isoformat() if isinstance(value, (Date, datetime))
            else float(value) if isinstance(value, Decimal)
            else value
            for value in parameters
        ))
        return QueryResult(cursor)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


def connection_string_for_database(database_name):
    parts = [part for part in SQLSERVER_CONNECTION_STRING.split(";") if part]
    replaced = False
    for index, part in enumerate(parts):
        if part.split("=", 1)[0].strip().lower() in {"database", "initial catalog"}:
            parts[index] = f"Database={database_name}"
            replaced = True
    if not replaced:
        parts.append(f"Database={database_name}")
    return ";".join(parts)


def ensure_database():
    if not SQLSERVER_CONNECTION_STRING:
        raise RuntimeError("SQLSERVER_CONNECTION_STRING must be set to connect to SQL Server.")
    if not re.fullmatch(r"[A-Za-z0-9_]+", SQLSERVER_DATABASE):
        raise RuntimeError("SQLSERVER_DATABASE may contain only letters, numbers, and underscores.")
    master_connection_string = connection_string_for_database("master")
    connection = pyodbc.connect(master_connection_string, autocommit=True, timeout=5)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "IF DB_ID(?) IS NULL BEGIN DECLARE @sql NVARCHAR(300) = N'CREATE DATABASE ' + QUOTENAME(?); EXEC(@sql); END",
            SQLSERVER_DATABASE,
            SQLSERVER_DATABASE,
        )
    finally:
        connection.close()


@contextmanager
def database():
    if not SQLSERVER_CONNECTION_STRING:
        raise RuntimeError("SQLSERVER_CONNECTION_STRING must be set to connect to SQL Server.")
    connection = DatabaseConnection(pyodbc.connect(
        connection_string_for_database(SQLSERVER_DATABASE),
        autocommit=False,
        timeout=5,
    ))
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
        statements = [
            """IF OBJECT_ID(N'users', N'U') IS NULL CREATE TABLE users (
                id NVARCHAR(36) NOT NULL PRIMARY KEY, name NVARCHAR(100) NOT NULL,
                email NVARCHAR(254) NOT NULL, password_hash NVARCHAR(255) NOT NULL,
                email_notifications BIT NOT NULL CONSTRAINT users_email_notifications_default DEFAULT 1,
                created_at DATETIME2 NOT NULL CONSTRAINT users_created_at_default DEFAULT SYSUTCDATETIME())""",
            """IF OBJECT_ID(N'expenses', N'U') IS NULL CREATE TABLE expenses (
                id NVARCHAR(36) NOT NULL PRIMARY KEY,
                user_id NVARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title NVARCHAR(160) NOT NULL, amount DECIMAL(12,2) NOT NULL CHECK (amount > 0),
                category NVARCHAR(32) NOT NULL, expense_date DATE NOT NULL,
                description NVARCHAR(1000) NOT NULL CONSTRAINT expenses_description_default DEFAULT '',
                expense_type NVARCHAR(16) NOT NULL CONSTRAINT expenses_type_default DEFAULT 'regular'
                    CHECK (expense_type IN ('regular', 'travel')),
                people NVARCHAR(100) NULL, created_at DATETIME2 NOT NULL CONSTRAINT expenses_created_at_default DEFAULT SYSUTCDATETIME())""",
            """IF OBJECT_ID(N'travelers', N'U') IS NULL CREATE TABLE travelers (
                id NVARCHAR(36) NOT NULL PRIMARY KEY,
                user_id NVARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name NVARCHAR(100) NOT NULL, email NVARCHAR(254) NOT NULL CONSTRAINT travelers_email_default DEFAULT '',
                image_data NVARCHAR(MAX) NULL,
                created_at DATETIME2 NOT NULL CONSTRAINT travelers_created_at_default DEFAULT SYSUTCDATETIME())""",
            """IF OBJECT_ID(N'user_settings', N'U') IS NULL CREATE TABLE user_settings (
                user_id NVARCHAR(36) NOT NULL PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                expense_limit DECIMAL(12,2) NULL, travel_limit DECIMAL(12,2) NULL)""",
            """IF OBJECT_ID(N'notifications', N'U') IS NULL CREATE TABLE notifications (
                id NVARCHAR(36) NOT NULL PRIMARY KEY,
                user_id NVARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind NVARCHAR(60) NOT NULL, title NVARCHAR(160) NOT NULL, message NVARCHAR(1000) NOT NULL,
                email_status NVARCHAR(32) NOT NULL CONSTRAINT notifications_email_status_default DEFAULT 'not_sent',
                is_read BIT NOT NULL CONSTRAINT notifications_is_read_default DEFAULT 0,
                created_at DATETIME2 NOT NULL CONSTRAINT notifications_created_at_default DEFAULT SYSUTCDATETIME())""",
            """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'users_email_lower_unique')
                CREATE UNIQUE INDEX users_email_lower_unique ON users(email)""",
            """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'expenses_user_date_idx')
                CREATE INDEX expenses_user_date_idx ON expenses(user_id, expense_date DESC)""",
            """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'travelers_user_name_unique')
                CREATE UNIQUE INDEX travelers_user_name_unique ON travelers(user_id, name)""",
            """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'notifications_user_date_idx')
                CREATE INDEX notifications_user_date_idx ON notifications(user_id, created_at DESC)""",
            "IF COL_LENGTH('travelers', 'email') IS NULL ALTER TABLE travelers ADD email NVARCHAR(254) NOT NULL CONSTRAINT travelers_email_migration_default DEFAULT ''",
            "IF COL_LENGTH('travelers', 'image_data') IS NULL ALTER TABLE travelers ADD image_data NVARCHAR(MAX) NULL",
            "IF COL_LENGTH('users', 'email_notifications') IS NULL ALTER TABLE users ADD email_notifications BIT NOT NULL CONSTRAINT users_email_notifications_migration_default DEFAULT 1",
        ]
        for statement in statements:
            connection.execute(statement)
        connection.execute("UPDATE notifications SET email_status = 'not_sent' WHERE email_status = 'pending'")


@app.on_event("startup")
def startup():
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET must be set to a random value with at least 32 characters.")
    ensure_database()
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
    except pyodbc.IntegrityError as error:
        if "users_email_lower_unique" not in str(error) and "duplicate key" not in str(error).lower():
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


@app.delete("/api/profile", status_code=204)
def delete_profile(user_id: UserId):
    with database() as connection:
        result = connection.execute("DELETE FROM users WHERE id = %s", (user_id,))
        if result.rowcount == 0:
            raise HTTPException(404, "Profile not found.")


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
        rows = connection.execute("SELECT id, name, email, image_data FROM travelers WHERE user_id = %s ORDER BY name", (user_id,)).fetchall()
    return [{"id": str(row["id"]), "name": row["name"], "email": row["email"], "image": row["image_data"]} for row in rows]


def validated_traveler_image(value):
    if value is None:
        return None
    match = re.fullmatch(r"data:image/(?:png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})", value)
    if not match:
        raise HTTPException(400, "Traveler photos must be PNG, JPEG, or WebP images.")
    try:
        image_bytes = base64.b64decode(match.group(1), validate=True)
    except ValueError as error:
        raise HTTPException(400, "The traveler photo is not valid base64 data.") from error
    if not image_bytes or len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(400, "Traveler photos must be between 1 byte and 5 MB.")
    return value


@app.post("/api/travelers", status_code=201)
def create_traveler(payload: TravelerInput, user_id: UserId):
    name = payload.name.strip()
    email = payload.email.strip().lower()
    if not name:
        raise HTTPException(400, "Enter a traveler name.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(400, "Enter a valid traveler email address.")
    image = validated_traveler_image(payload.image)
    try:
        with database() as connection:
            row = connection.execute(
                "SELECT id FROM travelers WHERE user_id = %s AND lower(name) = lower(%s)",
                (user_id, name),
            ).fetchone()
            if row:
                traveler_id = row["id"]
                row = connection.execute(
                    """UPDATE travelers SET email = %s, image_data = COALESCE(%s, image_data)
                       WHERE id = %s RETURNING id, name, email, image_data""",
                    (email, image, traveler_id),
                ).fetchone()
            else:
                row = connection.execute(
                    """INSERT INTO travelers (id, user_id, name, email, image_data)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id, name, email, image_data""",
                    (uuid4(), user_id, name, email, image),
                ).fetchone()
    except pyodbc.IntegrityError as error:
        if "travelers_user_name_unique" not in str(error) and "duplicate key" not in str(error).lower():
            raise
        raise HTTPException(409, "That traveler is already on your list.")
    return {"id": str(row["id"]), "name": row["name"], "email": row["email"], "image": row["image_data"]}


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
        existing = connection.execute("SELECT user_id FROM user_settings WHERE user_id = %s", (user_id,)).fetchone()
        if existing:
            connection.execute(
                """UPDATE user_settings SET
                    expense_limit = CASE WHEN %s = 1 THEN %s ELSE expense_limit END,
                    travel_limit = CASE WHEN %s = 1 THEN %s ELSE travel_limit END
                    WHERE user_id = %s""",
                ("expenseLimit" in values, values.get("expenseLimit"), "travelLimit" in values, values.get("travelLimit"), user_id),
            )
        else:
            connection.execute(
                "INSERT INTO user_settings (user_id, expense_limit, travel_limit) VALUES (%s, %s, %s)",
                (user_id, values.get("expenseLimit"), values.get("travelLimit")),
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
