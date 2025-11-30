import os
import shutil
import time
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from config import DUMP_CHAT_ID, OWNER_ID
from utils.aerofs_helper import write_stream_to_file
from utils.zip_helper import extract_zip

@Client.on_message(filters.regex(r"https?://www\.dropbox\.com/.*") & filters.user(OWNER_ID))
async def dropbox_handler(client: Client, message: Message):
    url = message.text.strip()
    if "?dl=0" in url:
        url = url.replace("?dl=0", "?dl=1")
    elif "?dl=1" not in url:
        if "?" in url:
            url += "&dl=1"
        else:
            url += "?dl=1"

    status_msg = await message.reply_text("Downloading from Dropbox...")
    
    temp_dir = f"downloads/{message.id}"
    os.makedirs(temp_dir, exist_ok=True)
    zip_path = f"{temp_dir}/download.zip"
    extract_path = f"{temp_dir}/extracted"

    try:
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    await status_msg.edit_text("Failed to download. Check the link.")
                    return
                
                await write_stream_to_file(response.content.iter_chunked(1024*1024), zip_path)
        
        download_time = time.time() - start_time
        await status_msg.edit_text(f"Downloaded in {download_time:.2f}s. Extracting...")

        await extract_zip(zip_path, extract_path)
        
        await status_msg.edit_text("Extracted. Uploading to Dump Channel...")

        files = []
        for root, dirs, filenames in os.walk(extract_path):
            for filename in filenames:
                files.append(os.path.join(root, filename))

        total_files = len(files)
        uploaded = 0

        for file_path in files:
            try:
                await client.send_document(
                    chat_id=DUMP_CHAT_ID,
                    document=file_path,
                    caption=f"Backup: {os.path.basename(file_path)}"
                )
                uploaded += 1
                if uploaded % 5 == 0:
                    await status_msg.edit_text(f"Uploading... {uploaded}/{total_files}")
            except Exception as e:
                print(f"Failed to upload {file_path}: {e}")

        await status_msg.edit_text(f"Done! Uploaded {uploaded}/{total_files} files.")

    except Exception as e:
        await status_msg.edit_text(f"Error: {str(e)}")
        print(f"Error processing dropbox link: {e}")
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Failed to cleanup {temp_dir}: {e}")
