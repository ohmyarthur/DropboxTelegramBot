from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    await message.reply_text(
        "Halo! Saya adalah bot backup Dropbox ke Telegram.\n"
        "Kirimkan link Dropbox (zip) untuk memulai proses backup."
    )
