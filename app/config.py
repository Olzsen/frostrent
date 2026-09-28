import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class Settings:
    main_bot_token:str
    admin_bot_token:str
    admin_ids:set[int]
    db_path:Path
    kosell_base_url:str
    real_rent_enabled:bool
    yoomoney_wallet:str
    yoomoney_secret:str
    public_base_url:str
    web_port:int

def load_settings():
    mt=os.getenv('MAIN_BOT_TOKEN','').strip(); at=os.getenv('ADMIN_BOT_TOKEN','').strip()
    if not mt: raise RuntimeError('MAIN_BOT_TOKEN не задан')
    if not at: raise RuntimeError('ADMIN_BOT_TOKEN не задан')
    admins={int(x.strip()) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip()}
    if not admins: raise RuntimeError('ADMIN_IDS не задан')
    db=Path(os.getenv('DB_PATH','./data/frostrent.sqlite3')).expanduser(); db.parent.mkdir(parents=True,exist_ok=True)
    rent=os.getenv('REAL_RENT_ENABLED','true').strip().lower() in {'1','true','yes','on','y'}
    return Settings(mt,at,admins,db,os.getenv('KOSELL_BASE_URL','https://kosell.store').rstrip('/'),rent,
        os.getenv('YOOMONEY_WALLET','').strip(),os.getenv('YOOMONEY_HTTP_SECRET','').strip(),
        os.getenv('PUBLIC_BASE_URL','').strip().rstrip('/'),int(os.getenv('WEB_PORT','8080')))
