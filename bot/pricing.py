DEVICE_PRICES = {
    1: 45, 2: 65, 3: 80, 4: 95, 5: 110,
    6: 125, 7: 135, 8: 150, 9: 165, 10: 175,
    11: 190, 12: 205, 13: 220, 14: 235, 15: 250,
}

DISCOUNT_TABLE = {
    1: 0, 2: 6, 3: 7, 4: 8, 5: 9, 6: 11,
    7: 12, 8: 13, 9: 14, 10: 15, 11: 16, 12: 17,
}


def get_device_price(n: int) -> int:
    if n <= 0:
        raise ValueError("Device count must be >= 1")
    if n <= 15:
        return DEVICE_PRICES[n]
    return 250 + (n - 15) * 30


def get_discount(months: int) -> int:
    if months <= 0:
        raise ValueError("Months must be >= 1")
    if months <= 12:
        return DISCOUNT_TABLE[months]
    return 20


def calculate_total(devices: int, months: int) -> int:
    price_per_month = get_device_price(devices)
    discount = get_discount(months)
    total = price_per_month * months * (1 - discount / 100)
    return round(total)
