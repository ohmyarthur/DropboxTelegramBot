import logging
import uvloop
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN

uvloop.install()

logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram.session.session").setLevel(logging.ERROR)

app = Client(
    "backup_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")
)

if __name__ == "__main__":
    print("Bot starting...")
    app.run()
