import os
import sqlite3
from pathlib import Path

from server.main import create_schema, database, ensure_database

source_path = Path(os.getenv("LEGACY_SQLITE_PATH", "server/expense_tracker.db"))
if not source_path.is_absolute():
    source_path = Path(__file__).resolve().parents[1] / source_path
if not source_path.is_file():
    raise FileNotFoundError(f"Legacy SQLite database not found: {source_path}")

source = sqlite3.connect(source_path)
source.row_factory = sqlite3.Row
ensure_database()
create_schema()
counts = {"users": 0, "travelers": 0, "user_settings": 0, "expenses": 0, "notifications": 0}
user_ids = {}

try:
    with database() as target:
        old_users = source.execute("SELECT * FROM users").fetchall()
        for old_user in old_users:
            old_id = str(old_user["id"])
            existing = target.execute("SELECT id FROM users WHERE id = %s", (old_id,)).fetchone()
            if existing is None:
                existing = target.execute("SELECT id FROM users WHERE lower(email) = %s", (old_user["email"].strip().lower(),)).fetchone()
            if existing:
                user_ids[old_id] = str(existing["id"])
                continue
            email_notifications = old_user["email_notifications"] if "email_notifications" in old_user.keys() else 1
            target.execute(
                """INSERT INTO users (id, name, email, password_hash, email_notifications)
                   VALUES (%s, %s, %s, %s, %s)""",
                (old_id, old_user["name"], old_user["email"].strip().lower(), old_user["password_hash"], bool(email_notifications)),
            )
            user_ids[old_id] = old_id
            counts["users"] += 1

        old_travelers = source.execute("SELECT * FROM travelers").fetchall()
        traveler_columns = {column[1] for column in source.execute("PRAGMA table_info(travelers)")}
        for traveler in old_travelers:
            user_id = user_ids[str(traveler["user_id"])]
            existing = target.execute(
                "SELECT id FROM travelers WHERE id = %s OR (user_id = %s AND lower(name) = lower(%s))",
                (str(traveler["id"]), user_id, traveler["name"]),
            ).fetchone()
            if existing:
                continue
            email = traveler["email"] if "email" in traveler_columns else ""
            image = traveler["image_data"] if "image_data" in traveler_columns else None
            target.execute(
                """INSERT INTO travelers (id, user_id, name, email, image_data)
                   VALUES (%s, %s, %s, %s, %s)""",
                (str(traveler["id"]), user_id, traveler["name"], email, image),
            )
            counts["travelers"] += 1

        if source.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'user_settings'").fetchone():
            for settings in source.execute("SELECT * FROM user_settings").fetchall():
                user_id = user_ids[str(settings["user_id"])]
                if target.execute("SELECT 1 FROM user_settings WHERE user_id = %s", (user_id,)).fetchone():
                    continue
                target.execute(
                    "INSERT INTO user_settings (user_id, expense_limit, travel_limit) VALUES (%s, %s, %s)",
                    (user_id, settings["expense_limit"], settings["travel_limit"]),
                )
                counts["user_settings"] += 1

        for expense in source.execute("SELECT * FROM expenses").fetchall():
            if target.execute("SELECT 1 FROM expenses WHERE id = %s", (str(expense["id"]),)).fetchone():
                continue
            target.execute(
                """INSERT INTO expenses
                   (id, user_id, title, amount, category, expense_date, description, expense_type, people)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(expense["id"]),
                    user_ids[str(expense["user_id"])],
                    expense["title"],
                    expense["amount"],
                    expense["category"],
                    expense["expense_date"],
                    expense["description"],
                    expense["expense_type"],
                    expense["people"],
                ),
            )
            counts["expenses"] += 1

        if source.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notifications'").fetchone():
            for notification in source.execute("SELECT * FROM notifications").fetchall():
                if target.execute("SELECT 1 FROM notifications WHERE id = %s", (str(notification["id"]),)).fetchone():
                    continue
                target.execute(
                    """INSERT INTO notifications
                       (id, user_id, kind, title, message, email_status, is_read)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (
                        str(notification["id"]),
                        user_ids[str(notification["user_id"])],
                        notification["kind"],
                        notification["title"],
                        notification["message"],
                        notification["email_status"],
                        bool(notification["is_read"]),
                    ),
                )
                counts["notifications"] += 1
finally:
    source.close()

print("SQLite migration finished. Newly copied rows: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
print("The original SQLite database was left unchanged.")
