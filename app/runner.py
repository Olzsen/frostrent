import asyncio,uvicorn
from aiogram import Bot,Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from .config import load_settings
from .db import Database
from .main_bot import register as register_main
from .admin_bot import register as register_admin
from .web import create_app
async def run_bot(bot,dp): await dp.start_polling(bot)
async def main():
    s=load_settings(); db=Database(s.db_path); main_bot=Bot(s.main_bot_token); admin_bot=Bot(s.admin_bot_token)
    mdp=Dispatcher(storage=MemoryStorage()); adp=Dispatcher(storage=MemoryStorage()); register_main(mdp,main_bot,db,s); register_admin(adp,admin_bot,db,s)
    config=uvicorn.Config(create_app(db,s,main_bot),host='0.0.0.0',port=s.web_port,log_level='info'); server=uvicorn.Server(config)
    await asyncio.gather(run_bot(main_bot,mdp),run_bot(admin_bot,adp),server.serve())
