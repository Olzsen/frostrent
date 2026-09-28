from aiogram import Dispatcher,Bot,F
from aiogram.filters import Command
from aiogram.types import Message,CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State,StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import html
from .db import Database
from .config import Settings
from .shared import is_admin,client,markup,maintenance
from .kosell import KOSellError
from .yoomoney import quickpay_url
class S(StatesGroup): api=State(); markup=State(); reply=State(); pay_edit=State()
def menu():
    kb=InlineKeyboardBuilder()
    for t,d in [('🔌 API KOSell','api'),('📦 Склад','stock'),('📈 Наценка','markup'),('🛠 Техработы','maintenance'),('👥 Пользователи','users'),('💰 Балансы','balances'),('💳 Пополнения','payments'),('📦 Активные аренды','rentals'),('↩️ Возвраты','refunds'),('🆘 Поддержка','support')]: kb.button(text=t,callback_data=d)
    kb.adjust(1); return kb.as_markup()
def back(): 
    kb=InlineKeyboardBuilder(); kb.button(text='⬅️ Назад',callback_data='back'); return kb.as_markup()
def register(dp:Dispatcher,bot:Bot,db:Database,s:Settings):
    @dp.message(Command('start'))
    async def start(m:Message):
        if not is_admin(m.from_user.id,s): return
        await m.answer('🔧 <b>FrostRent Admin</b>',reply_markup=menu(),parse_mode='HTML')
    @dp.callback_query()
    async def cb(c:CallbackQuery,state:FSMContext):
        if not is_admin(c.from_user.id,s): await c.answer(); return
        await c.answer(); d=c.data
        try:
            if d=='back': return await c.message.edit_text('🔧 <b>FrostRent Admin</b>',reply_markup=menu(),parse_mode='HTML')
            if d=='api':
                await state.set_state(S.api); return await c.message.answer('Введите KOSell API Key:',reply_markup=back())
            if d=='markup':
                await state.set_state(S.markup); return await c.message.answer(f'Текущая наценка: <b>{markup(db):.2f}%</b>\nВведите новую:',reply_markup=back(),parse_mode='HTML')
            if d=='maintenance':
                db.set('maintenance','0' if db.get('maintenance')=='1' else '1'); return await c.message.edit_text(f'Техработы: <b>{"ВКЛ" if db.get("maintenance")=="1" else "ВЫКЛ"}</b>',reply_markup=menu(),parse_mode='HTML')
            if d=='users': return await c.message.edit_text(f'👥 Пользователей: <b>{db.count_users()}</b>',reply_markup=back(),parse_mode='HTML')
            if d=='balances': return await c.message.edit_text(f'💰 Балансы пользователей: <b>{db.total_user_balances():.2f} ₽</b>',reply_markup=back(),parse_mode='HTML')
            if d=='stock':
                ps=await client(db,s).products(); lines=['📦 <b>Склад</b>','']
                for p in ps[:30]: lines.append(f"{html.escape(str(p.get('name','—')))} — {int(p.get('available_accounts') or 0)}")
                return await c.message.edit_text('\n'.join(lines),reply_markup=back(),parse_mode='HTML')
            if d=='rentals':
                rows=db.recent_rentals(25); lines=['📦 <b>Последние аренды</b>','']
                for r in rows: lines.append(f"#{r['id']} • {html.escape(str(r['product_name']))} • {r['price_paid_rub']:.2f} ₽")
                return await c.message.edit_text('\n'.join(lines) or 'Нет аренд.',reply_markup=back(),parse_mode='HTML')
            if d=='refunds':
                rows=db.recent_rentals(25); kb=InlineKeyboardBuilder(); lines=['↩️ <b>Возвраты</b>','']
                for r in rows:
                    if not int(r['refunded']): kb.button(text=f"↩️ #{r['id']} {str(r['product_name'])[:24]}",callback_data=f'refund:{r["id"]}')
                kb.button(text='⬅️ Назад',callback_data='back'); kb.adjust(1)
                return await c.message.edit_text('\n'.join(lines) or 'Нет аренд.',reply_markup=kb.as_markup(),parse_mode='HTML')
            if d.startswith('refund:'):
                rid=int(d.split(':')[1]); row=db.mark_refunded(rid)
                if not row:return await c.message.edit_text('Возврат уже выполнен или аренда не найдена.',reply_markup=menu())
                return await c.message.edit_text(f'✅ Возвращено <b>{float(row["price_paid_rub"]):.2f} ₽</b> пользователю <code>{row["telegram_id"]}</code>.',reply_markup=menu(),parse_mode='HTML')
            if d=='support':
                rows=db.open_tickets(30); kb=InlineKeyboardBuilder(); lines=['🆘 <b>Открытые тикеты</b>','']
                for r in rows: lines.append(f"#{r['id']} • <code>{r['telegram_id']}</code> • {r['created_at']}"); kb.button(text=f'↩️ #{r["id"]}',callback_data=f'reply:{r["id"]}')
                kb.button(text='⬅️ Назад',callback_data='back'); kb.adjust(1)
                return await c.message.edit_text('\n'.join(lines) or 'Открытых тикетов нет.',reply_markup=kb.as_markup(),parse_mode='HTML')
            if d.startswith('reply:'):
                tid=int(d.split(':')[1]); t=db.ticket(tid)
                if not t:return await c.message.answer('Тикет не найден.')
                await state.update_data(ticket_id=tid); await state.set_state(S.reply); return await c.message.answer(f'Ответ для тикета #{tid}:')
        except KOSellError as e: return await c.message.edit_text('⚠️ '+html.escape(str(e)),reply_markup=menu(),parse_mode='HTML')
    @dp.callback_query(F.data=='payments')
    async def payments(c:CallbackQuery):
        if not is_admin(c.from_user.id,s): return
        rows=db.recent_payments(20); kb=InlineKeyboardBuilder(); lines=['💳 <b>Пополнения</b>','']
        if not rows: lines.append('Пополнений пока нет.')
        for r in rows:
            status={'pending':'⏳','credited':'✅','cancelled':'❌'}.get(r['status'],'•')
            lines.append(f"{status} <code>{r['payment_id'][:10]}</code> • user <code>{r['telegram_id']}</code> • <b>{float(r['amount_rub']):.2f} ₽</b> • {r['status']}")
            if r['status']=='pending':
                kb.button(text=f"✏️ {r['payment_id'][:8]} изменить",callback_data=f'pedit:{r["payment_id"]}')
                kb.button(text=f"❌ {r["payment_id"][:8]} отменить",callback_data=f'pcancel:{r["payment_id"]}')
                kb.button(text=f"✅ {r["payment_id"][:8]} зачислить",callback_data=f'pcredit:{r["payment_id"]}')
        kb.button(text='⬅️ Назад',callback_data='back'); kb.adjust(1)
        await c.message.edit_text('\n'.join(lines),reply_markup=kb.as_markup(),parse_mode='HTML')
    @dp.callback_query(F.data.startswith('pcancel:'))
    async def payment_cancel(c:CallbackQuery):
        if not is_admin(c.from_user.id,s): return
        db.cancel_payment(c.data.split(':',1)[1]); await c.answer('Пополнение отменено'); return await c.message.edit_text('❌ Пополнение отменено.',reply_markup=menu(),parse_mode='HTML')
    @dp.callback_query(F.data.startswith('pcredit:'))
    async def payment_credit(c:CallbackQuery):
        if not is_admin(c.from_user.id,s): return
        pid=c.data.split(':',1)[1]; ok,uid,amount=db.credit_payment(pid)
        if ok and uid:
            try: await bot.send_message(uid,f'✅ Администратор зачислил пополнение: <b>+{amount:.2f} ₽</b>',parse_mode='HTML')
            except: pass
            return await c.message.edit_text(f'✅ Зачислено <b>{amount:.2f} ₽</b> пользователю <code>{uid}</code>.',reply_markup=menu(),parse_mode='HTML')
        await c.answer('Пополнение уже обработано или не найдено',show_alert=True)
    @dp.callback_query(F.data.startswith('pedit:'))
    async def payment_edit_start(c:CallbackQuery,state:FSMContext):
        if not is_admin(c.from_user.id,s): return
        pid=c.data.split(':',1)[1]; row=db.payment(pid)
        if not row or row['status']!='pending': return await c.answer('Можно менять только ожидающие пополнения',show_alert=True)
        await state.update_data(payment_id=pid); await state.set_state(S.pay_edit)
        await c.message.answer(f'✏️ Новая сумма для <code>{pid}</code>\nТекущая: <b>{float(row["amount_rub"]):.2f} ₽</b>\nВведите сумму в рублях.',parse_mode='HTML')
    @dp.message(S.pay_edit)
    async def payment_edit(m:Message,state:FSMContext):
        if not is_admin(m.from_user.id,s): return
        try: amount=round(float((m.text or '').replace(',','.')),2)
        except: return await m.answer('Введите сумму числом.')
        if amount<50: return await m.answer('Минимум 50 ₽.')
        data=await state.get_data(); pid=data['payment_id']; db.update_payment_amount(pid,amount); row=db.payment(pid); await state.clear()
        msg=f'✅ Сумма пополнения изменена на <b>{amount:.2f} ₽</b>.'
        if row and s.yoomoney_wallet and s.public_base_url:
            gross=round(amount/0.97,2)
            url=quickpay_url(s.yoomoney_wallet,gross,str(row['label']),s.public_base_url+'/payment/return')
            kb=InlineKeyboardBuilder(); kb.button(text='💳 Новая ссылка оплаты',url=url); kb.button(text='💳 Пополнения',callback_data='payments'); kb.adjust(1)
            try: await bot.send_message(int(row['telegram_id']),f'💳 <b>Сумма пополнения изменена администратором</b>\n\nК оплате: <b>{gross:.2f} ₽</b>\nНа баланс: <b>{amount:.2f} ₽</b>.',reply_markup=kb.as_markup(),parse_mode='HTML')
            except: pass
            return await m.answer(msg+' Новая ссылка отправлена пользователю.',reply_markup=menu(),parse_mode='HTML')
        await m.answer(msg,reply_markup=menu(),parse_mode='HTML')
    @dp.message(S.api)
    async def api(m:Message,state:FSMContext):
        if not is_admin(m.from_user.id,s): return
        v=(m.text or '').strip(); db.set('kosell_api_key',v); await state.clear(); await m.answer('✅ API Key сохранён.',reply_markup=menu())
    @dp.message(S.markup)
    async def mk(m:Message,state:FSMContext):
        if not is_admin(m.from_user.id,s): return
        try:v=float((m.text or '').replace(',','.'))
        except:return await m.answer('Введите число.')
        if not 0<=v<=100000:return await m.answer('Диапазон 0–100000%.')
        db.set('markup_percent',v); await state.clear(); await m.answer(f'✅ Наценка: {v:.2f}%',reply_markup=menu())
    @dp.message(S.reply)
    async def reply(m:Message,state:FSMContext):
        if not is_admin(m.from_user.id,s): return
        data=await state.get_data(); tid=int(data['ticket_id']); t=db.ticket(tid)
        if not t: await state.clear(); return await m.answer('Тикет не найден.')
        text=m.text or m.caption or '[медиа]'; db.add_support_message(tid,m.from_user.id,text,True)
        try: await bot.send_message(int(t['telegram_id']),f'🆘 <b>Ответ поддержки #{tid}</b>\n\n{html.escape(text)}',parse_mode='HTML')
        except: pass
        await state.clear(); await m.answer('✅ Ответ отправлен.',reply_markup=menu())
