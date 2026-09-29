import hashlib, hmac
from urllib.parse import quote

def _rfc3986(value):
    return quote(str(value), safe="-_.~")

def quickpay_url(wallet: str, amount: float, label: str, success_url: str = "") -> str:
    parts = [
        "https://yoomoney.ru/quickpay/confirm?",
        "receiver=" + _rfc3986(wallet),
        "quickpay-form=button",
        "targets=" + _rfc3986("Пополнение баланса FrostRent"),
        "paymentType=AC",
        "sum=" + _rfc3986(f"{amount:.2f}"),
        "label=" + _rfc3986(label),
    ]
    if success_url:
        parts.append("successURL=" + _rfc3986(success_url))
    return "&".join(parts)

def notification_signature_payload(form: dict) -> str:
    data = [(str(k), str(v)) for k, v in form.items() if str(k) != "sign"]
    data.sort(key=lambda item: item[0])
    return "&".join(f"{_rfc3986(k)}={_rfc3986(v)}" for k, v in data)

def notification_signature(form: dict, secret: str) -> str:
    payload = notification_signature_payload(form)
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest().lower()

def verify_notification(form: dict, secret: str) -> bool:
    supplied = str(form.get("sign") or "").strip().lower()
    if not supplied or not secret:
        return False
    expected = notification_signature(form, secret)
    return hmac.compare_digest(expected, supplied)
