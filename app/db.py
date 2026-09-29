import sqlite3
from pathlib import Path

class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def conn(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        return c

    def init(self):
        with self.conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, username TEXT, first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            c.execute("CREATE TABLE IF NOT EXISTS balances (telegram_id INTEGER PRIMARY KEY, balance_rub REAL NOT NULL DEFAULT 0)")
            c.execute("""CREATE TABLE IF NOT EXISTS user_rentals (
                id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, rental_uid TEXT NOT NULL UNIQUE,
                product_id INTEGER, product_name TEXT, duration_hours INTEGER, price_paid_rub REAL DEFAULT 0,
                refunded INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY, telegram_id INTEGER NOT NULL, amount_rub REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', label TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                credited_at TEXT, yoomoney_operation_id TEXT
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS balance_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, kind TEXT NOT NULL,
                amount_rub REAL NOT NULL, reference TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open',
                subject TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, closed_at TEXT
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL, telegram_id INTEGER NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0, text TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            cols={r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
            if "ref_code" not in cols: c.execute("ALTER TABLE users ADD COLUMN ref_code TEXT")
            if "referred_by" not in cols: c.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
            rcols={r[1] for r in c.execute("PRAGMA table_info(user_rentals)").fetchall()}
            if "refunded" not in rcols: c.execute("ALTER TABLE user_rentals ADD COLUMN refunded INTEGER NOT NULL DEFAULT 0")
            pcols={r[1] for r in c.execute("PRAGMA table_info(payments)").fetchall()}
            if "label" not in pcols: c.execute("ALTER TABLE payments ADD COLUMN label TEXT")
            if "yoomoney_operation_id" not in pcols: c.execute("ALTER TABLE payments ADD COLUMN yoomoney_operation_id TEXT")
            c.commit()

    def get(self,k):
        with self.conn() as c:
            r=c.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone()
            return r[0] if r else None
    def topup_min(self):
        try: return max(1.0, round(float(self.get("topup_min") or 50), 2))
        except (TypeError, ValueError): return 50.0
    def set_topup_min(self, amount):
        amount=round(float(amount), 2)
        if amount < 1: raise ValueError("minimum topup must be at least 1")
        self.set("topup_min", amount)
    def set(self,k,v):
        with self.conn() as c:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(v))); c.commit()
    def user(self,uid,username,referral_code=None):
        with self.conn() as c:
            row=c.execute("SELECT telegram_id,ref_code,referred_by FROM users WHERE telegram_id=?",(uid,)).fetchone()
            if not row:
                ref_code=f"r{uid}"; referred_by=None
                if referral_code:
                    ref=referral_code.strip().lower().removeprefix("ref_")
                    owner=c.execute("SELECT telegram_id FROM users WHERE ref_code=?",(ref,)).fetchone()
                    if owner and int(owner[0])!=int(uid): referred_by=int(owner[0])
                c.execute("INSERT INTO users(telegram_id,username,ref_code,referred_by) VALUES(?,?,?,?)",(uid,username,ref_code,referred_by))
            else: c.execute("UPDATE users SET username=COALESCE(?,username) WHERE telegram_id=?",(username,uid))
            c.execute("INSERT OR IGNORE INTO balances(telegram_id,balance_rub) VALUES(?,0)",(uid,)); c.commit()
    def user_ref_code(self,uid):
        with self.conn() as c:
            r=c.execute("SELECT ref_code FROM users WHERE telegram_id=?",(uid,)).fetchone()
            return str(r[0]) if r and r[0] else f"r{uid}"
    def referrer(self,uid):
        with self.conn() as c:
            r=c.execute("SELECT referred_by FROM users WHERE telegram_id=?",(uid,)).fetchone()
            return int(r[0]) if r and r[0] else None
    def referral_count(self,uid):
        with self.conn() as c: return int(c.execute("SELECT COUNT(*) FROM users WHERE referred_by=?",(uid,)).fetchone()[0])
    def count_users(self):
        with self.conn() as c: return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    def balance(self,uid):
        with self.conn() as c:
            r=c.execute("SELECT balance_rub FROM balances WHERE telegram_id=?",(uid,)).fetchone()
            return float(r[0]) if r else 0.0
    def credit(self,uid,amount,reference,kind="credit"):
        if amount<=0: raise ValueError("amount must be positive")
        with self.conn() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT OR IGNORE INTO balances(telegram_id,balance_rub) VALUES(?,0)",(uid,))
            c.execute("UPDATE balances SET balance_rub=balance_rub+? WHERE telegram_id=?",(amount,uid))
            c.execute("INSERT INTO balance_transactions(telegram_id,kind,amount_rub,reference) VALUES(?,?,?,?)",(uid,kind,amount,reference))
            c.commit()
    def debit(self,uid,amount,reference):
        if amount<=0: raise ValueError("amount must be positive")
        with self.conn() as c:
            c.execute("BEGIN IMMEDIATE"); c.execute("INSERT OR IGNORE INTO balances(telegram_id,balance_rub) VALUES(?,0)",(uid,))
            cur=c.execute("UPDATE balances SET balance_rub=balance_rub-? WHERE telegram_id=? AND balance_rub>=?",(amount,uid,amount))
            if cur.rowcount!=1: c.rollback(); return False
            c.execute("INSERT INTO balance_transactions(telegram_id,kind,amount_rub,reference) VALUES(?,?,?,?)",(uid,'debit',amount,reference)); c.commit(); return True
    def refund(self,uid,amount,reference): self.credit(uid,amount,reference,kind="refund")
    def add_payment(self,payment_id,uid,amount,label):
        with self.conn() as c:
            c.execute("INSERT OR IGNORE INTO payments(payment_id,telegram_id,amount_rub,status,label) VALUES(?,?,?,'pending',?)",(payment_id,uid,amount,label)); c.commit()
    def payment(self,payment_id):
        with self.conn() as c: return c.execute("SELECT * FROM payments WHERE payment_id=?",(payment_id,)).fetchone()
    def payment_by_label(self,label):
        with self.conn() as c: return c.execute("SELECT * FROM payments WHERE label=?",(label,)).fetchone()
    def recent_payments(self,limit=30):
        with self.conn() as c: return c.execute("SELECT * FROM payments ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
    def pending_payments(self,limit=100):
        with self.conn() as c: return c.execute("SELECT * FROM payments WHERE status='pending' ORDER BY created_at ASC LIMIT ?",(limit,)).fetchall()
    def update_payment_amount(self,payment_id,amount):
        with self.conn() as c:
            cur=c.execute("UPDATE payments SET amount_rub=? WHERE payment_id=? AND status='pending'",(amount,payment_id)); c.commit()
            return cur.rowcount==1
    def cancel_payment(self,payment_id):
        with self.conn() as c:
            cur=c.execute("UPDATE payments SET status='cancelled' WHERE payment_id=? AND status='pending'",(payment_id,)); c.commit()
            return cur.rowcount==1
    def credit_payment_from_yoomoney(self,payment_id,received_amount,operation_id):
        with self.conn() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT * FROM payments WHERE payment_id=?",(payment_id,)).fetchone()
            if not row: c.rollback(); return False,None,None,"not_found"
            if row["status"]=="credited":
                c.rollback(); return False,int(row["telegram_id"]),float(row["amount_rub"]),"already_credited"
            if row["status"]!="pending":
                c.rollback(); return False,int(row["telegram_id"]),float(row["amount_rub"]),"not_pending"
            expected=round(float(row["amount_rub"]),2)
            received=round(float(received_amount),2)
            if abs(received-expected)>0.01:
                c.rollback(); return False,int(row["telegram_id"]),expected,"amount_mismatch"
            op=str(operation_id or "").strip()
            if op:
                seen=c.execute("SELECT payment_id FROM payments WHERE yoomoney_operation_id=?",(op,)).fetchone()
                if seen:
                    c.rollback(); return False,int(row["telegram_id"]),expected,"duplicate_operation"
            uid=int(row["telegram_id"])
            c.execute("INSERT OR IGNORE INTO balances(telegram_id,balance_rub) VALUES(?,0)",(uid,))
            c.execute("UPDATE balances SET balance_rub=balance_rub+? WHERE telegram_id=?",(expected,uid))
            c.execute("UPDATE payments SET status='credited',credited_at=CURRENT_TIMESTAMP,yoomoney_operation_id=? WHERE payment_id=?",(op or None,payment_id))
            c.execute("INSERT INTO balance_transactions(telegram_id,kind,amount_rub,reference) VALUES(?,?,?,?)",(uid,'credit',expected,f'yoomoney:{payment_id}:{op or "unknown"}'))
            c.commit()
            return True,uid,expected,"credited"
    def transactions(self,uid,limit=20):
        with self.conn() as c: return c.execute("SELECT kind,amount_rub,reference,created_at FROM balance_transactions WHERE telegram_id=? ORDER BY id DESC LIMIT ?",(uid,limit)).fetchall()
    def add_rental(self,uid,rental_uid,pid,name,hours,price_paid_rub):
        with self.conn() as c:
            c.execute("INSERT OR IGNORE INTO user_rentals(telegram_id,rental_uid,product_id,product_name,duration_hours,price_paid_rub) VALUES(?,?,?,?,?,?)",(uid,rental_uid,pid,name,hours,price_paid_rub)); c.commit()
    def rentals(self,uid):
        with self.conn() as c: return c.execute("SELECT * FROM user_rentals WHERE telegram_id=? ORDER BY id DESC",(uid,)).fetchall()
    def recent_rentals(self,limit=30):
        with self.conn() as c: return c.execute("SELECT r.*,u.username FROM user_rentals r LEFT JOIN users u ON u.telegram_id=r.telegram_id ORDER BY r.id DESC LIMIT ?",(limit,)).fetchall()
    def mark_refunded(self,rental_id):
        with self.conn() as c:
            c.execute("BEGIN IMMEDIATE"); row=c.execute("SELECT * FROM user_rentals WHERE id=?",(rental_id,)).fetchone()
            if not row or int(row['refunded']): c.rollback(); return None
            amount=float(row['price_paid_rub']); uid=int(row['telegram_id'])
            c.execute("UPDATE user_rentals SET refunded=1 WHERE id=?",(rental_id,))
            c.execute("INSERT OR IGNORE INTO balances(telegram_id,balance_rub) VALUES(?,0)",(uid,))
            c.execute("UPDATE balances SET balance_rub=balance_rub+? WHERE telegram_id=?",(amount,uid))
            c.execute("INSERT INTO balance_transactions(telegram_id,kind,amount_rub,reference) VALUES(?,?,?,?)",(uid,'refund',amount,f'refund:rental:{row["rental_uid"]}')); c.commit(); return row
    def count_rentals(self):
        with self.conn() as c: return c.execute("SELECT COUNT(*) FROM user_rentals").fetchone()[0]
    def total_user_balances(self):
        with self.conn() as c: return float(c.execute("SELECT COALESCE(SUM(balance_rub),0) FROM balances").fetchone()[0])
    def create_ticket(self,uid,subject='Поддержка'):
        with self.conn() as c:
            cur=c.execute("INSERT INTO support_tickets(telegram_id,subject) VALUES(?,?)",(uid,subject)); c.commit(); return int(cur.lastrowid)
    def add_support_message(self,ticket_id,uid,text,is_admin=False):
        with self.conn() as c:
            row=c.execute("SELECT status FROM support_tickets WHERE id=?",(ticket_id,)).fetchone()
            if not row or row["status"]!="open": return False
            c.execute("INSERT INTO support_messages(ticket_id,telegram_id,is_admin,text) VALUES(?,?,?,?)",(ticket_id,uid,int(is_admin),text)); c.commit(); return True
    def open_ticket(self,uid):
        with self.conn() as c: return c.execute("SELECT * FROM support_tickets WHERE telegram_id=? AND status='open' ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
    def open_tickets(self,limit=30):
        with self.conn() as c: return c.execute("SELECT * FROM support_tickets WHERE status='open' ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
    def support_history(self,tid,limit=50):
        with self.conn() as c: return c.execute("SELECT * FROM support_messages WHERE ticket_id=? ORDER BY id ASC LIMIT ?",(tid,limit)).fetchall()
    def ticket(self,tid):
        with self.conn() as c: return c.execute("SELECT * FROM support_tickets WHERE id=?",(tid,)).fetchone()
    def close_ticket(self,tid):
        with self.conn() as c:
            cur=c.execute("UPDATE support_tickets SET status='closed',closed_at=CURRENT_TIMESTAMP WHERE id=? AND status='open'",(tid,)); c.commit()
            return cur.rowcount==1
