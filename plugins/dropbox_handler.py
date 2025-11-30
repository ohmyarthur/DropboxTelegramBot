import os
import shutil
import time
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
import asyncio
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
            concurrency=16,
            progress_callback=None
        )
        
        await status_msg.edit_text("Downloading with Aria2c...")
        await downloader.download()
        await downloader.close()
        
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
                if filename.lower().endswith('.json'):
                    continue
                files.append(os.path.join(root, filename))

        total_files = len(files)
        uploaded = 0
        
        upload_prog = Progress(status_msg, total_files, "Uploading Files")

        for i, file_path in enumerate(files):
            filename = os.path.basename(file_path)
            ext = os.path.splitext(filename)[1].lower()
            caption = f"Backup: {filename}"
            
            file_size = os.path.getsize(file_path)
            if file_size > 1.9 * 1024 * 1024 * 1024: # 1.9GB
                if ext in ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.3gp', '.ts']:
                    await status_msg.edit_text(f"Compressing {filename} (Size: {file_size / (1024*1024*1024):.2f} GB)...")
                    compressed_path = f"{file_path}_compressed.mp4"
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "ffmpeg", "-i", file_path, "-c:v", "libx264", "-crf", "28", "-preset", "fast", "-c:a", "aac", "-b:a", "128k", compressed_path,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                        )
                        await proc.wait()
                        
                        if proc.returncode == 0 and os.path.exists(compressed_path):
                            if os.path.getsize(compressed_path) < 2 * 1024 * 1024 * 1024:
                                file_path = compressed_path
                                filename = os.path.basename(file_path)
                                caption = f"Backup (Compressed): {filename}"
                                ext = os.path.splitext(filename)[1].lower()
                            else:
                                print(f"Compression failed to reduce size enough for {filename}")
                        else:
                            print(f"FFmpeg failed for {filename}")
                    except Exception as e:
                        print(f"Compression error: {e}")

            while True:
                try:
                    if ext in ['.jpg', '.jpeg', '.png', '.heic', '.webp', '.tiff', '.bmp', '.gif']:
                        await client.send_photo(
                            chat_id=DUMP_CHAT_ID,
                            photo=file_path,
                            caption=caption,
                            progress=lambda current, total: None
                        )
                    elif ext in ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.3gp', '.ts']:
                        await client.send_video(
                            chat_id=DUMP_CHAT_ID,
                            video=file_path,
                            caption=caption,
                            supports_streaming=True,
                            progress=lambda current, total: None
                        )
                    else:
                        await client.send_document(
                            chat_id=DUMP_CHAT_ID,
                            document=file_path,
                            caption=caption,
                            progress=lambda current, total: None
                        )
                    
                    uploaded += 1
                    await upload_prog.update(uploaded)
                    
                    if file_path.endswith("_compressed.mp4"):
                         try:
                             os.remove(file_path)
                         except:
                             pass
                             
                    break

                except FloodWait as e:
                    print(f"FloodWait: Sleeping for {e.value} seconds...")
                    await asyncio.sleep(e.value)
                except Exception as e:
                    print(f"Failed to upload {file_path}: {e}")
                    break

        await status_msg.edit_text(f"Done! Uploaded {uploaded}/{total_files} files.")

    except Exception as e:
        await status_msg.edit_text(f"Error: {str(e)}")
        print(f"Error processing dropbox link: {e}")
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Failed to cleanup {temp_dir}: {e}")
