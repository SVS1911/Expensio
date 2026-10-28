import hashlib
import json
from pathlib import Path
from uuid import uuid4

from pwdlib import PasswordHash

from server.main import create_schema, database

source_path = Path(__file__).resolve().parents[1] / "db.json"
source_content = source_path.read_bytes()
source = json.loads(source_content)
source_hash = hashlib.sha256(source_content).hexdigest()
hasher = PasswordHash.recommended()
user_ids = {}

create_schema()
with database() as connection:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_imports (
            source_hash TEXT PRIMARY KEY,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    already_imported = connection.execute(
        "SELECT 1 FROM legacy_imports WHERE source_hash = %s",
        (source_hash,),
    ).fetchone()
    if already_imported:
        print("This exact db.json file was already imported; no data was changed.")
        raise SystemExit(0)

    for legacy_user in source.get("users", []):
        email = str(legacy_user.get("email", "")).strip().lower()
        password = str(legacy_user.get("password", ""))
        if not email or not password:
            raise ValueError(f"Legacy user {legacy_user.get('id', '(without id)')} is missing an email or password.")

        existing = connection.execute("SELECT id FROM users WHERE lower(email) = %s", (email,)).fetchone()
        if existing:
            user_ids[str(legacy_user.get("id"))] = existing["id"]
            continue

        user_id = uuid4()
        connection.execute(
            """
            INSERT INTO users (id, name, email, password_hash)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, str(legacy_user.get("name") or "User").strip()[:100], email, hasher.hash(password)),
        )
        user_ids[str(legacy_user.get("id"))] = str(user_id)

    for legacy_expense in source.get("expenses", []):
        user_id = user_ids.get(str(legacy_expense.get("user")))
        if not user_id:
            raise ValueError(f"Expense {legacy_expense.get('id', '(without id)')} refers to an unknown legacy user.")
        is_travel = legacy_expense.get("expenseType") == "travel"
        person = str(legacy_expense.get("people") or "").strip()[:100] if is_travel else None
        if is_travel and person:
            connection.execute(
                """
                INSERT INTO travelers (id, user_id, name, email)
                VALUES (%s, %s, %s, '') ON CONFLICT DO NOTHING
                """,
                (uuid4(), user_id, person),
            )
        connection.execute(
            """
            INSERT INTO expenses
              (id, user_id, title, amount, category, expense_date, description, expense_type, people)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                user_id,
                str(legacy_expense.get("title") or "").strip()[:160],
                round(float(legacy_expense["amount"]), 2),
                str(legacy_expense.get("category") or "Other")[:32],
                legacy_expense["date"],
                str(legacy_expense.get("description") or "")[:1000],
                "travel" if is_travel else "regular",
                person,
            ),
        )
    connection.execute(
        "INSERT INTO legacy_imports (source_hash) VALUES (%s)",
        (source_hash,),
    )

print(
    f"Imported {len(source.get('users', []))} users and "
    f"{len(source.get('expenses', []))} expenses. The legacy JSON file was left unchanged."
)
