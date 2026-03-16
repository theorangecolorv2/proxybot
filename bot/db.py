import aiosqlite
from datetime import datetime, timedelta, timezone
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                secret TEXT,
                username TEXT,
                created_at TEXT,
                expires_at TEXT,
                active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                yookassa_payment_id TEXT UNIQUE,
                amount TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT
            )
        """)
        await db.commit()

        # Migrations: add new columns idempotently
        for table, column, coltype, default in [
            ("subscriptions", "devices", "INTEGER", 1),
            ("subscriptions", "months", "INTEGER", 1),
            ("payments", "devices", "INTEGER", 1),
            ("payments", "months", "INTEGER", 1),
            ("users", "trial_used", "INTEGER", 0),
            ("users", "referred_by", "INTEGER", "NULL"),
            ("users", "referral_rewarded", "INTEGER", 0),
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {coltype} DEFAULT {default}"
                )
                await db.commit()
            except Exception:
                pass


async def add_user(telegram_id: int, username: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, created_at) VALUES (?, ?, ?)",
            (telegram_id, username, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def has_used_trial(telegram_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT trial_used FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return bool(row and row[0])


async def mark_trial_used(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET trial_used = 1 WHERE telegram_id = ?",
            (telegram_id,),
        )
        await db.commit()


async def add_trial_subscription(telegram_id: int, secret: str, username: str):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=3)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO subscriptions (telegram_id, secret, username, created_at, expires_at, active, devices, months) VALUES (?, ?, ?, ?, ?, 1, 1, 0)",
            (telegram_id, secret, username, now.isoformat(), expires.isoformat()),
        )
        await db.commit()


async def add_subscription(telegram_id: int, secret: str, username: str, devices: int = 1, months: int = 1):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=months * 30)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO subscriptions (telegram_id, secret, username, created_at, expires_at, active, devices, months) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (telegram_id, secret, username, now.isoformat(), expires.isoformat(), devices, months),
        )
        await db.commit()


async def get_active_subscriptions(telegram_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, secret, username, created_at, expires_at, devices, months FROM subscriptions WHERE telegram_id = ? AND active = 1",
            (telegram_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_expired_subscriptions() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, telegram_id, secret, username FROM subscriptions WHERE expires_at < ? AND active = 1",
            (now,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def deactivate_subscription(sub_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET active = 0 WHERE id = ?",
            (sub_id,),
        )
        await db.commit()


async def create_payment(telegram_id: int, yookassa_payment_id: str, amount: str, devices: int = 1, months: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO payments (telegram_id, yookassa_payment_id, amount, status, created_at, devices, months) VALUES (?, ?, ?, 'pending', ?, ?, ?)",
            (telegram_id, yookassa_payment_id, amount, datetime.now(timezone.utc).isoformat(), devices, months),
        )
        await db.commit()


async def get_payment_by_yookassa_id(yookassa_payment_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM payments WHERE yookassa_payment_id = ?",
            (yookassa_payment_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_payment_status(yookassa_payment_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status = ? WHERE yookassa_payment_id = ?",
            (status, yookassa_payment_id),
        )
        await db.commit()


# --- Referral ---

async def set_referrer(telegram_id: int, referrer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET referred_by = ? WHERE telegram_id = ? AND referred_by IS NULL",
            (referrer_id, telegram_id),
        )
        await db.commit()


async def get_referrer(telegram_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT referred_by FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None


async def get_referral_count(telegram_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def has_referral_rewarded(telegram_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT referral_rewarded FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return bool(row and row[0])


async def mark_referral_rewarded(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET referral_rewarded = 1 WHERE telegram_id = ?",
            (telegram_id,),
        )
        await db.commit()


async def add_referral_subscription(telegram_id: int, secret: str, username: str, days: int):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=days)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO subscriptions (telegram_id, secret, username, created_at, expires_at, active, devices, months) VALUES (?, ?, ?, ?, ?, 1, 1, 0)",
            (telegram_id, secret, username, now.isoformat(), expires.isoformat()),
        )
        await db.commit()
