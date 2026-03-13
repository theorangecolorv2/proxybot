import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TELEMT_API_URL = os.getenv("TELEMT_API_URL", "http://127.0.0.1:9091")
PROXY_HOST = os.getenv("PROXY_HOST", "82.148.28.80")
PROXY_PORT = int(os.getenv("PROXY_PORT", "443"))
TLS_DOMAIN = os.getenv("TLS_DOMAIN", "petrovich.ru")
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
DB_PATH = os.getenv("DB_PATH", "/app/data/bot.db")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_API_KEY = os.getenv("YOOKASSA_API_KEY", "")
YOOKASSA_WEBHOOK_PORT = int(os.getenv("YOOKASSA_WEBHOOK_PORT", "8080"))
PROXY_PRICE = os.getenv("PROXY_PRICE", "100.00")
