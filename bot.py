import logging
import uvloop
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN

# Install uvloop
uvloop.install()

logging.basicConfig(level=logging.INFO)

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
