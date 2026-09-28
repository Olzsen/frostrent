from fastapi import FastAPI,Request
from fastapi.responses import HTMLResponse,JSONResponse
from .db import Database
from .yoomoney import verify_notification

def create_app(db,settings,main_bot=None):
    app=FastAPI(title='FrostRent webhook',docs_url=None,redoc_url=None)
    @app.get('/health')
    async def health(): return {'status':'ok'}
    @app.get('/payment/return',response_class=HTMLResponse)
    async def ret(): return HTMLResponse('<html><body style="font-family:Arial;padding:40px"><h2>Оплата получена</h2><p>Вернитесь в Telegram. Баланс будет обновлён после подтверждения перевода.</p></body></html>')
    @app.post('/yoomoney/webhook')
    async def yoomoney(request:Request):
        form=dict(await request.form())
        if not verify_notification(form,settings.yoomoney_secret): return JSONResponse({'ok':False},status_code=403)
        if str(form.get('notification_type')) not in {'p2p-incoming','card-incoming'}: return JSONResponse({'ok':True})
        if str(form.get('currency'))!='643': return JSONResponse({'ok':True})
        label=str(form.get('label') or '')
        row=db.payment_by_label(label)
        if not row: return JSONResponse({'ok':True})
        try: amount=round(float(form.get('amount') or 0),2)
        except: return JSONResponse({'ok':True})
        expected_net=round(float(row['amount_rub']),2)
        if abs(amount-expected_net)>0.01: return JSONResponse({'ok':True})
        credited,uid,added=db.credit_payment(row['payment_id'],expected_net)
        if credited and main_bot and uid:
            try: await main_bot.send_message(uid,f'Баланс пополнен: +{added:.2f} ₽')
            except: pass
        return JSONResponse({'ok':True})
    return app
