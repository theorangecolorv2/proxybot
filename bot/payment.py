import uuid
from yookassa import Configuration, Payment
from config import YOOKASSA_SHOP_ID, YOOKASSA_API_KEY
from pricing import calculate_total

Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_API_KEY


def create_yookassa_payment(telegram_id: int, devices: int, months: int) -> dict:
    total = calculate_total(devices, months)
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
        "description": f"Прокси: {devices} устр., {months} мес.",
        "metadata": {
            "telegram_id": str(telegram_id),
            "devices": str(devices),
            "months": str(months),
        },
    }, uuid.uuid4())

    return {
        "payment_id": payment.id,
        "confirmation_url": payment.confirmation.confirmation_url,
        "amount": str(total),
    }
