import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TELEMT_API_URL = os.getenv("TELEMT_API_URL", "http://127.0.0.1:9091")
PROXY_HOST = os.getenv("PROXY_HOST", "5.188.140.104")
PROXY_PORT = int(os.getenv("PROXY_PORT", "443"))
TLS_DOMAIN = os.getenv("TLS_DOMAIN", "petrovich.ru")
DB_PATH = os.getenv("DB_PATH", "/app/data/bot.db")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_API_KEY = os.getenv("YOOKASSA_API_KEY", "")
YOOKASSA_WEBHOOK_PORT = int(os.getenv("YOOKASSA_WEBHOOK_PORT", "8080"))
RECEIPT_EMAIL = os.getenv("RECEIPT_EMAIL", "noreply@example.com")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "586107799,762967142").split(",")))
