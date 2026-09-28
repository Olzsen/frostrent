import html
from .db import Database
from .kosell import KOSellClient, KOSellError

def is_admin(uid,settings): return uid in settings.admin_ids
def key(db): return db.get('kosell_api_key')
def markup(db):
    try: return max(0,min(100000,float(db.get('markup_percent') or 0)))
    except: return 0.0
def maintenance(db): return db.get('maintenance')=='1'
def client(db,settings):
    k=key(db)
    if not k: raise KOSellError('Магазин пока не настроен.')
    return KOSellClient(k,settings.kosell_base_url)
def maintenance_text(): return '🛠 <b>Технические работы</b>\n\nМагазин временно недоступен. Попробуйте позже.'
