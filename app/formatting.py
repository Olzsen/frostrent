def money(v,c="₽"):
    try: return f"{float(v):.2f} {c}"
    except: return f"— {c}"

def marked(v,p):
    try: return round(float(v)*(1+p/100),2)
    except: return 0.0

def stock(p):
    n=int(p.get('available_accounts') or 0)
    if n>0: return f"🟢 В наличии: <b>{n}</b>"
    nxt=p.get('next_available') or []
    if nxt: return f"🟡 Нет свободных • ближайшее: <b>{nxt[0].get('available_in_human') or 'скоро'}</b>"
    return "🔴 Нет свободных аккаунтов"
