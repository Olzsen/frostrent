from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from .yoomoney import verify_notification

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
        form = dict(await request.form())
        if not verify_notification(form, settings.yoomoney_secret):
            return HTMLResponse("invalid signature", status_code=403)
        if str(form.get("notification_type") or "") not in {"p2p-incoming","card-incoming"}:
            return HTMLResponse("ok", status_code=200)
        if str(form.get("currency") or "") != "643":
            return HTMLResponse("ok", status_code=200)
        if str(form.get("unaccepted") or "").lower() == "true":
            return HTMLResponse("ok", status_code=200)
        label = str(form.get("label") or "").strip()
        operation_id = str(form.get("operation_id") or "").strip()
        if not label or not operation_id:
            return HTMLResponse("ok", status_code=200)
        row = db.payment_by_label(label)
        if not row:
            return HTMLResponse("ok", status_code=200)
        try:
            received = round(float(str(form.get("amount") or "0").replace(",",".")), 2)
        except (TypeError, ValueError):
            return HTMLResponse("ok", status_code=200)
        ok, uid, amount, reason = db.credit_payment_from_yoomoney(row["payment_id"], received, operation_id)
        if ok and main_bot and uid:
            try:
                await main_bot.send_message(uid, f"✅ Баланс пополнен: <b>+{amount:.2f} ₽</b>", parse_mode="HTML")
            except Exception:
                pass
        return HTMLResponse("ok", status_code=200)
    return app
