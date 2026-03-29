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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notifications_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER,
                notification_type TEXT,
                sent_at TEXT,
                UNIQUE(subscription_id, notification_type)
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


async def get_active_subscription(telegram_id: int) -> dict | None:
    """Get the latest-expiring active subscription for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, secret, username, created_at, expires_at, devices, months FROM subscriptions WHERE telegram_id = ? AND active = 1 ORDER BY expires_at DESC LIMIT 1",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def extend_subscription(sub_id: int, months: int = 0, days: int = 0, devices: int | None = None):
    """Extend an existing subscription by N months and/or days. Optionally update devices count."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT expires_at FROM subscriptions WHERE id = ?", (sub_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return
        current_expires = datetime.fromisoformat(row[0])
        now = datetime.now(timezone.utc)
        base = max(current_expires, now)
        new_expires = base + timedelta(days=months * 30 + days)
        updates = "expires_at = ?"
        params: list = [new_expires.isoformat()]
        if devices is not None:
            updates += ", devices = ?"
            params.append(devices)
        params.append(sub_id)
        await db.execute(
            f"UPDATE subscriptions SET {updates} WHERE id = ?", params,
        )
        await db.commit()


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


# --- Notifications ---

async def get_all_active_subscriptions() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, telegram_id, expires_at FROM subscriptions WHERE active = 1",
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def was_notification_sent(subscription_id: int, notification_type: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM notifications_sent WHERE subscription_id = ? AND notification_type = ?",
            (subscription_id, notification_type),
        )
        return await cursor.fetchone() is not None


async def mark_notification_sent(subscription_id: int, notification_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO notifications_sent (subscription_id, notification_type, sent_at) VALUES (?, ?, ?)",
            (subscription_id, notification_type, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


# --- Admin stats ---

async def get_users_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0]


async def get_active_subscriptions_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM subscriptions WHERE active = 1")
        row = await cursor.fetchone()
        return row[0]


async def get_payments_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM payments WHERE status = 'succeeded'")
        row = await cursor.fetchone()
        paid_count = row[0]
        cursor = await db.execute("SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM payments WHERE status = 'succeeded'")
        row = await cursor.fetchone()
        total_revenue = row[0]
        return {"paid_count": paid_count, "total_revenue": total_revenue}


async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT telegram_id FROM users ORDER BY rowid")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
