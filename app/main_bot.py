import html, uuid
from aiogram import Dispatcher, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .db import Database
from .config import Settings
from .shared import client, maintenance, maintenance_text, markup
from .formatting import marked, money, stock
from .kosell import KOSellError
from .state import ORDERS, Order
from .yoomoney import quickpay_url
from .yoomoney_checker import check_payment_now

DEFAULT_TOPUP=50.0
REF_PERCENT=1.0

class S(StatesGroup):
    topup=State()
    search=State()
    support=State()

def menu():
    kb=InlineKeyboardBuilder()
    for t,d in [('🎮 Каталог','catalog'),('🔎 Поиск','search'),('💰 Баланс','balance'),('🎁 Рефералы','refs'),('📦 Мои аренды','rentals'),('🆘 Поддержка','support')]:
        kb.button(text=t,callback_data=d)
    kb.adjust(1); return kb.as_markup()

def balance_kb():
    kb=InlineKeyboardBuilder(); kb.button(text='➕ Пополнить',callback_data='topup'); kb.button(text='📜 История',callback_data='history'); kb.button(text='🏠 Меню',callback_data='home'); kb.adjust(1); return kb.as_markup()

def register(dp:Dispatcher, bot:Bot, admin_bot:Bot, db:Database, s:Settings):
    async def show_balance(c):
        await safe(c,f'💰 <b>Баланс</b>\n\n<b>{db.balance(c.from_user.id):.2f} ₽</b>',balance_kb())

    @dp.message(Command('start'))
    async def start(m:Message):
        arg=(m.text or '').partition(' ')[2].strip()
        db.user(m.from_user.id,m.from_user.username,arg)
        if maintenance(db): return await m.answer(maintenance_text(),parse_mode='HTML')
        await m.answer('👋 <b>FrostRent</b>\n\nВыберите раздел.',reply_markup=menu(),parse_mode='HTML')

    @dp.message(Command('catalog'))
    async def catalog(m:Message):
        if maintenance(db): return await m.answer(maintenance_text(),parse_mode='HTML')
        await catalog_msg(m,db,s)

    @dp.callback_query(F.data=='home')
    async def home(c:CallbackQuery): await c.answer(); await safe(c,'🏠 <b>FrostRent</b>\n\nВыберите раздел.',menu())

    @dp.callback_query(F.data=='balance')
    async def balance(c:CallbackQuery): await c.answer(); await show_balance(c)

    @dp.callback_query(F.data=='topup')
    async def topup(c:CallbackQuery,state:FSMContext):
        await c.answer(); await state.set_state(S.topup)
        minimum=db.topup_min()
        await c.message.answer(f'➕ Введите сумму пополнения. Минимум <b>{minimum:.2f} ₽</b>.',parse_mode='HTML')

    @dp.message(S.topup)
    async def topup_amount(m:Message,state:FSMContext):
        try: amount=round(float((m.text or '').replace(',','.')),2)
        except: return await m.answer('❌ Введите сумму числом.')
        minimum=db.topup_min()
        if amount<minimum: return await m.answer(f'❌ Минимум {minimum:.2f} ₽.')
        if not s.yoomoney_wallet or not s.yoomoney_api_token:
            await state.clear(); return await m.answer('⚠️ Пополнение временно недоступно.')
        pid=uuid.uuid4().hex
        label='FROST-'+pid
        db.add_payment(pid,m.from_user.id,amount,label)
        gross=round(amount/0.97,2)
        success_url=s.public_base_url+'/payment/return' if s.public_base_url else ''
        url=quickpay_url(s.yoomoney_wallet,gross,label,success_url)
        kb=InlineKeyboardBuilder()
        kb.button(text='💳 Оплатить',url=url)
        kb.button(text='🔄 Проверить оплату',callback_data=f'checkpay:{pid}')
        kb.button(text='💰 Баланс',callback_data='balance')
        kb.adjust(1)
        await state.clear()
        await m.answer(f'💳 К оплате: <b>{gross:.2f} ₽</b>\nНа баланс будет зачислено: <b>{amount:.2f} ₽</b>.',reply_markup=kb.as_markup(),parse_mode='HTML')

    @dp.callback_query(F.data.startswith('checkpay:'))
    async def checkpay(c:CallbackQuery):
        await c.answer('Проверяю оплату…')
        payment_id=c.data.split(':',1)[1]
        row=db.payment(payment_id)
        if not row or int(row['telegram_id'])!=int(c.from_user.id):
            return await safe(c,'❌ Платёж не найден.',balance_kb())
        if row['status']=='credited':
            return await safe(c,f'✅ <b>Платёж уже зачислен</b>\n\nСумма: <b>{float(row["amount_rub"]):.2f} ₽</b>',balance_kb())
        if not s.yoomoney_api_token:
            return await safe(c,'⚠️ Проверка платежа временно недоступна.',balance_kb())
        try:
            ok, uid, amount, reason=await check_payment_now(db,s.yoomoney_api_token,payment_id)
        except Exception:
            return await safe(c,'⚠️ Не удалось проверить платёж. Попробуйте ещё раз чуть позже.',balance_kb())
        if ok:
            return await safe(c,f'✅ <b>Баланс пополнен</b>\n\n<b>+{amount:.2f} ₽</b>',balance_kb())
        if reason=='amount_mismatch':
            return await safe(c,'⚠️ Платёж найден, но сумма не совпадает с ожидаемой. Баланс не изменён.',balance_kb())
        return await safe(c,'⏳ Оплата пока не найдена. После оплаты нажмите «Проверить оплату» ещё раз.',balance_kb())

    @dp.callback_query(F.data=='history')
    async def history(c:CallbackQuery):
        await c.answer(); rows=db.transactions(c.from_user.id,15)
        lines=['📜 <b>История</b>','']+[f"{'−' if r['kind']=='debit' else '+'} {float(r['amount_rub']):.2f} ₽ • {html.escape(str(r['reference'] or ''))[:50]}" for r in rows]
        await safe(c,'\n'.join(lines) if rows else '📜 История пуста.',balance_kb())

    @dp.callback_query(F.data=='refs')
    async def refs(c:CallbackQuery):
        await c.answer(); me=await bot.get_me(); code=db.user_ref_code(c.from_user.id); link=f'https://t.me/{me.username}?start=ref_{code}'
        await safe(c,f'🎁 <b>Рефералы</b>\n\nРефералов: <b>{db.referral_count(c.from_user.id)}</b>\nКомиссия: <b>{REF_PERCENT:.0f}%</b>\n\n<code>{html.escape(link)}</code>',menu())

    @dp.callback_query(F.data=='catalog')
    async def catalog_cb(c:CallbackQuery):
        await c.answer(); await catalog_edit(c,db,s,0)

    @dp.callback_query(F.data.startswith('page:'))
    async def page(c:CallbackQuery):
        await c.answer(); await catalog_edit(c,db,s,int(c.data.split(':')[1]))

    @dp.callback_query(F.data.startswith('product:'))
    async def product(c:CallbackQuery):
        await c.answer(); pid=int(c.data.split(':')[1]); ps=await client(db,s).products(); p=next((x for x in ps if int(x.get('id'))==pid),None)
        if not p:return await safe(c,'❌ Товар не найден.',menu())
        kb=InlineKeyboardBuilder(); kb.button(text='🛒 Арендовать',callback_data=f'rent:{pid}'); kb.button(text='⬅️ Каталог',callback_data='catalog'); kb.adjust(1)
        await safe(c,f"🎮 <b>{html.escape(str(p.get('name','—')))}</b>\n\n{stock(p)}\n\n💰 <b>{money(marked(p.get('price_per_hour_rub',0),markup(db)))}</b>/ч\n⏱ {p.get('min_hours','—')}–{p.get('max_hours','—')} ч.",kb.as_markup())

    @dp.callback_query(F.data.startswith('rent:'))
    async def rent(c:CallbackQuery):
        await c.answer(); pid=int(c.data.split(':')[1]); ps=await client(db,s).products(); p=next((x for x in ps if int(x.get('id'))==pid),None)
        if not p:return await safe(c,'❌ Товар не найден.',menu())
        kb=InlineKeyboardBuilder(); mn=int(p.get('min_hours') or 1); mx=int(p.get('max_hours') or 1)
        for h in [1,3,6,12,24,48,72,168]:
            if mn<=h<=mx: kb.button(text=f'⏱ {h} ч.',callback_data=f'quote:{pid}:{h}')
        kb.button(text='⬅️ Назад',callback_data=f'product:{pid}'); kb.adjust(2)
        await safe(c,'⏱ <b>Выберите срок</b>',kb.as_markup())

    @dp.callback_query(F.data.startswith('quote:'))
    async def quote(c:CallbackQuery):
        await c.answer(); _,pid,h=c.data.split(':'); pid=int(pid); h=int(h)
        ps=await client(db,s).products(); p=next((x for x in ps if int(x.get('id'))==pid),None); q=await client(db,s).quote(pid,h)
        price=marked(float(q.get('total_rub') or 0),markup(db)); ORDERS[c.from_user.id]=Order(pid,str(p.get('name','—')),h,q,price)
        kb=InlineKeyboardBuilder(); kb.button(text='💳 Оплатить с баланса',callback_data='pay'); kb.button(text='❌ Отмена',callback_data='cancel'); kb.adjust(1)
        await safe(c,f'🧾 <b>Заказ</b>\n\n🎮 {html.escape(str(p.get("name","—")))}\n⏱ {h} ч.\n💰 <b>{price:.2f} ₽</b>\n💳 Баланс: <b>{db.balance(c.from_user.id):.2f} ₽</b>',kb.as_markup())

    @dp.callback_query(F.data=='cancel')
    async def cancel(c:CallbackQuery): ORDERS.pop(c.from_user.id,None); await c.answer(); await safe(c,'❌ Заказ отменён.',menu())

    @dp.callback_query(F.data=='pay')
    async def pay(c:CallbackQuery):
        await c.answer(); o=ORDERS.get(c.from_user.id)
        if not o:return await safe(c,'❌ Заказ устарел.',menu())
        ref='rent:'+uuid.uuid4().hex
        if not db.debit(c.from_user.id,o.price_rub,ref): return await safe(c,'❌ Недостаточно средств.',balance_kb())
        try:r=await client(db,s).rent(o.product_id,o.hours,'RUB',uuid.uuid4().hex)
        except KOSellError:
            db.refund(c.from_user.id,o.price_rub,ref+':refund'); return await safe(c,'❌ Аренда не создана. Средства возвращены.',menu())
        uid=str(r.get('rental_uid')); db.add_rental(c.from_user.id,uid,o.product_id,o.product_name,o.hours,o.price_rub)
        referrer=db.referrer(c.from_user.id)
        if referrer: db.credit(referrer,round(o.price_rub*REF_PERCENT/100,2),'referral:'+uid,'referral')
        try:
            cr=await client(db,s).credentials(uid)
            msg=f"🔐 <b>Логин:</b> <code>{html.escape(str(cr.get('steam_login','—')))}</code>\n<b>Пароль:</b> <code>{html.escape(str(cr.get('steam_password','—')))}</code>"
        except: msg='🔐 Данные аккаунта пока недоступны.'
        ORDERS.pop(c.from_user.id,None); await safe(c,f'✅ <b>Аренда создана</b>\n\n🎮 {html.escape(o.product_name)}\n⏱ {o.hours} ч.\n🆔 <code>{uid}</code>',menu()); await c.message.answer(msg,parse_mode='HTML')

    @dp.callback_query(F.data=='rentals')
    async def rentals(c:CallbackQuery):
        await c.answer(); rows=db.rentals(c.from_user.id)
        if not rows:return await safe(c,'📦 Аренд пока нет.',menu())
        lines=['📦 <b>Мои аренды</b>','']+[f"#{r['id']} • {html.escape(str(r['product_name']))} • {r['duration_hours']} ч. • {float(r['price_paid_rub']):.2f} ₽"+(' • ↩️ возвращено' if r['refunded'] else '') for r in rows[:20]]
        await safe(c,'\n'.join(lines),menu())

    @dp.callback_query(F.data=='support')
    async def support(c:CallbackQuery,state:FSMContext):
        await c.answer()
        existing=db.open_ticket(c.from_user.id)
        if existing:
            await safe(c,f'🆘 <b>Тикет #{existing["id"]}</b> уже открыт. Новое обращение можно отправить после ответа/закрытия текущего тикета.',menu()); return
        tid=db.create_ticket(c.from_user.id)
        await state.set_state(S.support)
        await c.message.answer(f'🆘 <b>Тикет #{tid}</b>\n\nОпишите проблему одним сообщением. После отправки тикет уйдёт в панель администратора.',parse_mode='HTML')

    @dp.message(S.support)
    async def support_msg(m:Message,state:FSMContext):
        t=db.open_ticket(m.from_user.id)
        if not t:
            await state.clear(); return await m.answer('❌ Этот тикет уже закрыт. Откройте поддержку заново.',reply_markup=menu())
        text=m.text or m.caption or '[медиа]'
        if not db.add_support_message(int(t['id']),m.from_user.id,text,False):
            await state.clear(); return await m.answer('❌ Этот тикет уже закрыт.',reply_markup=menu())
        for aid in s.admin_ids:
            try:
                kb=InlineKeyboardBuilder()
                kb.button(text=f'↩️ Ответить #{t["id"]}',callback_data=f'reply:{t["id"]}')
                kb.button(text=f'✅ Закрыть #{t["id"]}',callback_data=f'close:{t["id"]}')
                kb.adjust(1)
                await admin_bot.send_message(aid,f'🆘 <b>Новый тикет #{t["id"]}</b>\n👤 <code>{m.from_user.id}</code>\n\n{html.escape(text)}',reply_markup=kb.as_markup(),parse_mode='HTML')
            except Exception:
                pass
        await state.clear()
        await m.answer(f'✅ Тикет #{t["id"]} отправлен в поддержку.',reply_markup=menu())

    @dp.message(S.search)
    async def search(m:Message,state:FSMContext):
        q=(m.text or '').strip(); await state.clear()
        try:
            ps=await client(db,s).products(q)
            ps=sort_products(ps,db)
            kb=InlineKeyboardBuilder()
            for p in ps[:15]: kb.button(text='🎮 '+str(p.get('name',''))[:35],callback_data=f'product:{p.get("id")}')
            kb.adjust(1); await m.answer(f'🔎 Найдено: <b>{len(ps)}</b>',reply_markup=kb.as_markup(),parse_mode='HTML')
        except KOSellError: await m.answer('⚠️ Поиск временно недоступен.')

    @dp.callback_query(F.data=='search')
    async def search_start(c:CallbackQuery,state:FSMContext): await c.answer(); await state.set_state(S.search); await c.message.answer('🔎 Введите название игры.')

    @dp.errors()
    async def errors(event): return True

async def catalog_msg(m,db,s):
    try:
        ps=sort_products(await client(db,s).products(),db)
        await m.answer(catalog_text(ps,0,db),reply_markup=catalog_kb(ps,0),parse_mode='HTML')
    except KOSellError as e: await m.answer('⚠️ '+html.escape(str(e)),parse_mode='HTML')

async def catalog_edit(c,db,s,page):
    try:
        ps=sort_products(await client(db,s).products(),db)
        await safe(c,catalog_text(ps,page,db),catalog_kb(ps,page))
    except KOSellError as e: await safe(c,'⚠️ '+html.escape(str(e)),menu())

def sort_products(ps,db):
    def popularity(p):
        for key in ('rent_count','rental_count','sales_count','sold_count','orders_count','popularity'):
            try:
                if p.get(key) is not None: return float(p.get(key))
            except: pass
        for key in ('available_accounts','stock'):
            try:
                if p.get(key) is not None: return 0.0
            except: pass
        return 0.0
    return sorted(list(ps),key=popularity,reverse=True)

def catalog_text(ps,page,db):
    size=6; pages=max(1,(len(ps)+size-1)//size); page=max(0,min(page,pages-1))
    lines=[f'🎮 <b>Каталог</b> • {page+1}/{pages}','🔥 Сначала самые популярные','']
    for p in ps[page*size:(page+1)*size]:
        indicator='🟢' if int(p.get('available_accounts') or 0)>0 else '🔴'
        lines.append(f"{indicator} <b>{html.escape(str(p.get('name','—')))}</b> • {int(p.get('available_accounts') or 0)} шт. • {marked(p.get('price_per_hour_rub',0),markup(db)):.2f} ₽/ч")
    return '\n'.join(lines)

def catalog_kb(ps,page):
    size=6; pages=max(1,(len(ps)+size-1)//size); page=max(0,min(page,pages-1)); kb=InlineKeyboardBuilder()
    for p in ps[page*size:(page+1)*size]:
        indicator='🟢' if int(p.get('available_accounts') or 0)>0 else '🔴'
        kb.button(text=indicator+' '+str(p.get('name',''))[:36],callback_data=f'product:{p.get("id")}')
    if page: kb.button(text='◀️',callback_data=f'page:{page-1}')
    if page<pages-1: kb.button(text='▶️',callback_data=f'page:{page+1}')
    kb.button(text='🏠 Меню',callback_data='home'); kb.adjust(1,2,1); return kb.as_markup()

async def safe(c,text,markup=None):
    try: await c.message.edit_text(text,reply_markup=markup,parse_mode='HTML')
    except: await c.message.answer(text,reply_markup=markup,parse_mode='HTML')
