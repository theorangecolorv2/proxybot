import uuid
from yookassa import Configuration, Payment
from config import YOOKASSA_SHOP_ID, YOOKASSA_API_KEY, PROXY_PRICE

Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_API_KEY


def create_yookassa_payment(telegram_id: int) -> dict:
    """Create a YooKassa payment and return payment id + confirmation url."""
    payment = Payment.create({
        "amount": {
            "value": PROXY_PRICE,
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me",
        },
        "capture": True,
        "description": f"Прокси подписка (30 дней) — tg:{telegram_id}",
        "metadata": {
            "telegram_id": str(telegram_id),
        },
    }, uuid.uuid4())

    return {
        "payment_id": payment.id,
        "confirmation_url": payment.confirmation.confirmation_url,
    }
