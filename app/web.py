import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from .yoomoney import verify_notification

logger = logging.getLogger("frostrent.yoomoney")

def _short(value, limit=120):
    value = str(value or "")
    return value if len(value) <= limit else value[:limit] + "..."

def create_app(db, settings, main_bot=None):
    app = FastAPI(title="FrostRent webhook", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/payment/return", response_class=HTMLResponse)
    async def payment_return():
        return HTMLResponse("<html><body style='font-family:Arial;padding:40px'><h2>Оплата получена</h2><p>Вернитесь в Telegram. Баланс будет обновлён после подтверждения перевода.</p></body></html>")

    @app.post("/yoomoney/webhook")
    async def yoomoney_webhook(request: Request):
        form_data = await request.form()
        form = {str(k): str(v) for k, v in form_data.items()}

        signature_ok = verify_notification(form, settings.yoomoney_secret)
        notification_type = str(form.get("notification_type") or "")
        operation_id = str(form.get("operation_id") or "").strip()
        label = str(form.get("label") or "").strip()
        amount_raw = str(form.get("amount") or "").replace(",", ".")
        withdraw_raw = str(form.get("withdraw_amount") or "").replace(",", ".")
        test_notification = str(form.get("test_notification") or "").lower() == "true"

        logger.info(
            "YooMoney webhook type=%s op=%s amount=%s withdraw=%s currency=%s label=%s test=%s signature_ok=%s",
            notification_type, operation_id, amount_raw, withdraw_raw,
            form.get("currency"), _short(label), test_notification, signature_ok
        )

        if not signature_ok:
            logger.warning("YooMoney webhook rejected: invalid signature")
            return HTMLResponse("invalid signature", status_code=403)

        if test_notification:
            return HTMLResponse("ok", status_code=200)

        if notification_type not in {"p2p-incoming", "card-incoming"}:
            logger.info("YooMoney webhook ignored: unsupported notification_type=%s", notification_type)
            return HTMLResponse("ok", status_code=200)

        if str(form.get("currency") or "") != "643":
            logger.info("YooMoney webhook ignored: currency=%s", form.get("currency"))
            return HTMLResponse("ok", status_code=200)

        if str(form.get("unaccepted") or "").lower() == "true":
            logger.info("YooMoney webhook ignored: unaccepted=true")
            return HTMLResponse("ok", status_code=200)

        if not label or not operation_id:
            logger.warning("YooMoney webhook ignored: missing label or operation_id")
            return HTMLResponse("ok", status_code=200)

        row = db.payment_by_label(label)
        if not row:
            logger.warning("YooMoney webhook ignored: unknown label=%s", _short(label))
            return HTMLResponse("ok", status_code=200)

        try:
            received = round(float(amount_raw or "0"), 2)
        except (TypeError, ValueError):
            logger.warning("YooMoney webhook ignored: invalid amount=%s", amount_raw)
            return HTMLResponse("ok", status_code=200)

        expected = round(float(row["amount_rub"]), 2)
        if abs(received - expected) > 0.01:
            logger.warning(
                "YooMoney webhook amount mismatch payment=%s expected=%.2f received=%.2f withdraw=%s",
                row["payment_id"], expected, received, withdraw_raw
            )
            return HTMLResponse("ok", status_code=200)

        ok, uid, credited_amount, reason = db.credit_payment_from_yoomoney(
            row["payment_id"], received, operation_id
        )
        logger.info(
            "YooMoney credit payment=%s uid=%s amount=%s reason=%s",
            row["payment_id"], uid, credited_amount, reason
        )

        if ok and main_bot and uid:
            try:
                await main_bot.send_message(
                    uid,
                    f"✅ Баланс пополнен: <b>+{credited_amount:.2f} ₽</b>",
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception("Failed to notify user %s about YooMoney credit", uid)

        return HTMLResponse("ok", status_code=200)

    return app
