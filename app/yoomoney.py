import hashlib, hmac
from urllib.parse import urlencode

class YooMoneyError(Exception): pass

def quickpay_url(wallet: str, amount: float, label: str, success_url: str = "") -> str:
    params = {
        'receiver': wallet,
        'quickpay-form': 'shop',
        'targets': 'Пополнение баланса FrostRent',
        'paymentType': 'AC',
        'sum': f'{amount:.2f}',
        'label': label,
    }
    if success_url:
        params['successURL'] = success_url
    return 'https://yoomoney.ru/quickpay/confirm?' + urlencode(params)

def verify_notification(form: dict, secret: str) -> bool:
    supplied = str(form.get('sign') or '').lower()
    if not supplied or not secret:
        return False
    data = {str(k): str(v) for k,v in form.items() if str(k) != 'sign'}
    encoded = urlencode(sorted(data.items()))
    digest = hmac.new(secret.encode('utf-8'), encoded.encode('utf-8'), hashlib.sha256).hexdigest().lower()
    return hmac.compare_digest(digest, supplied)
