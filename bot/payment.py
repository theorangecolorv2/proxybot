import uuid
from yookassa import Configuration, Payment
from config import YOOKASSA_SHOP_ID, YOOKASSA_API_KEY, RECEIPT_EMAIL
from pricing import calculate_total

Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_API_KEY


def create_yookassa_payment(telegram_id: int, devices: int, months: int, username: str | None = None) -> dict:
    total = calculate_total(devices, months)

    if username:
        description = f"@{username} (ID: {telegram_id}) — прокси {devices} устр., {months} мес."
    else:
        description = f"ID: {telegram_id} — прокси {devices} устр., {months} мес."

    payment = Payment.create({
        "amount": {
            "value": f"{total}.00",
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me",
        },
        "capture": True,
        "description": description,
        "metadata": {
            "telegram_id": str(telegram_id),
            "devices": str(devices),
            "months": str(months),
        },
        "receipt": {
            "customer": {
                "email": RECEIPT_EMAIL,
            },
            "items": [
                {
                    "description": f"Прокси Telegram: {devices} устр., {months} мес.",
                    "quantity": "1",
                    "amount": {
                        "value": f"{total}.00",
                        "currency": "RUB",
                    },
                    "vat_code": 1,
                    "payment_subject": "service",
                    "payment_mode": "full_payment",
                },
            ],
        },
    }, uuid.uuid4())

    return {
        "payment_id": payment.id,
        "confirmation_url": payment.confirmation.confirmation_url,
        "amount": str(total),
    }
