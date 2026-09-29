import hashlib, hmac
from urllib.parse import quote, urlparse

def _rfc3986(value):
    return quote(str(value), safe="-_.~")

def quickpay_url(wallet: str, amount: float, label: str, success_url: str = "") -> str:
    parts = [
        "https://yoomoney.ru/quickpay/confirm?",
        "receiver=" + _rfc3986(wallet),
        "quickpay-form=shop",
        "targets=" + _rfc3986("Пополнение баланса FrostRent"),
        "paymentType=AC",
        "sum=" + _rfc3986(f"{amount:.2f}"),
        "label=" + _rfc3986(label),
    ]
    if success_url:
        parts.append("successURL=" + _rfc3986(success_url))
    return "&".join(parts)

def verify_notification(form: dict, secret: str) -> bool:
    supplied = str(form.get("sign") or "").strip().lower()
    if not supplied or not secret:
        return False
    data = [(str(k), str(v)) for k,v in form.items() if str(k) != "sign"]
    data.sort(key=lambda item: item[0])
    canonical = "&".join(f"{_rfc3986(k)}={_rfc3986(v)}" for k,v in data)
    expected = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest().lower()
    return hmac.compare_digest(expected, supplied)
