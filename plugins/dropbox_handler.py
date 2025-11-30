import os
import shutil
import time
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from config import DUMP_CHAT_ID, OWNER_ID
from utils.aerofs_helper import write_stream_to_file
from utils.zip_helper import extract_zip
from utils.progress import Progress

@Client.on_message(filters.regex(r"https?://(www\.)?(dropbox\.com|.*\.dl\.dropboxusercontent\.com)/.*") & filters.user(OWNER_ID))
async def dropbox_handler(client: Client, message: Message):
    url = message.text.strip()
    
    if "dropbox.com" in url:
        if "?dl=0" in url:
            url = url.replace("?dl=0", "?dl=1")
        elif "?dl=1" not in url:
            if "?" in url:
                url += "&dl=1"
            else:
                url += "?dl=1"
    
    elif "dl.dropboxusercontent.com" in url:
        if "?dl=1" not in url:
            if "?" in url:
                url += "&dl=1"
            else:
                url += "?dl=1"

    status_msg = await message.reply_text("Initializing...")
    
    temp_dir = f"downloads/{message.id}"
    os.makedirs(temp_dir, exist_ok=True)
    zip_path = f"{temp_dir}/download.zip"
    extract_path = f"{temp_dir}/extracted"

    try:
        from utils.downloader import SmartDownloader        
        downloader = SmartDownloader(
            url, 
            zip_path, 
            concurrency=32,
            progress_callback=lambda current: progress.update(current) if 'progress' in locals() else None
        )
        
        async with aiohttp.ClientSession() as session:
             async with session.head(url, allow_redirects=True) as response:
                total_size = int(response.headers.get('Content-Length', 0))

        progress = Progress(status_msg, total_size, "Downloading (Multi-stream)")
        
        downloader.progress_callback = lambda current: progress.update(current)
        
        await downloader.download()
        
        await status_msg.edit_text("Download complete. Extracting...")
        async def extract_progress(current, total):
            if not hasattr(extract_progress, 'prog'):
                 extract_progress.prog = Progress(status_msg, total, "Extracting")
            await extract_progress.prog.update(current)

        await extract_zip(zip_path, extract_path, progress_callback=extract_progress)
        
        await status_msg.edit_text("Extracted. Uploading to Dump Channel...")

        files = []
        for root, dirs, filenames in os.walk(extract_path):
            for filename in filenames:
                files.append(os.path.join(root, filename))

        total_files = len(files)
        uploaded = 0
        
        upload_prog = Progress(status_msg, total_files, "Uploading Files")

        for i, file_path in enumerate(files):
            try:
                await client.send_document(
                    chat_id=DUMP_CHAT_ID,
                    document=file_path,
                    caption=f"Backup: {os.path.basename(file_path)}",
                    progress=lambda current, total: None
                )
                uploaded += 1
                await upload_prog.update(uploaded)
                
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
