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
from PIL import Image
import pillow_heif

pillow_heif.register_heif_opener()

VIDEO_FORMATS = ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.3gp', '.ts', '.mpg', '.mpeg', '.m2ts', '.mts']
IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.tiff', '.tif', '.bmp', '.gif']
MAX_TELEGRAM_SIZE = 1.95 * 1024 * 1024 * 1024
IMAGE_QUALITY = 85
VIDEO_CRF_H265 = 24

async def compress_image(input_path: str, output_path: str, max_quality: int = IMAGE_QUALITY) -> bool:
    try:
        img = Image.open(input_path)
        
        exif_data = img.info.get('exif', None)
        
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        
        file_size = os.path.getsize(input_path)
        
        if file_size < 500 * 1024:  # < 500KB
            img.save(output_path, 'PNG', optimize=True)
        else:
            save_params = {
                'format': 'JPEG',
                'quality': max_quality,
                'optimize': True,
                'progressive': True,  # Progressive loading untuk web
                'subsampling': 0,  # 4:4:4 chroma subsampling untuk quality maksimal
            }
            if exif_data:
                save_params['exif'] = exif_data
            
            img.save(output_path, **save_params)
        
        if os.path.exists(output_path):
            original_size = os.path.getsize(input_path)
            compressed_size = os.path.getsize(output_path)
            
            if compressed_size >= original_size * 0.95:
                shutil.copy2(input_path, output_path)
            
            return True
        return False
    except Exception as e:
        print(f"Image compression error: {e}")
        try:
            shutil.copy2(input_path, output_path)
            return True
        except:
            return False

async def compress_video_h265(input_path: str, output_path: str, status_msg: Message = None) -> bool:

    try:
        if status_msg:
            await status_msg.edit_text(f"🎬 Compressing video with H.265/HEVC (Near-Lossless Quality)...")
        
        cmd = [
            "ffmpeg", "-i", input_path,
            "-c:v", "libx265",
            "-crf", str(VIDEO_CRF_H265),
            "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-tag:v", "hvc1",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y",
            output_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await proc.communicate()
        
        if proc.returncode == 0 and os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            original_size = os.path.getsize(input_path)
            
            if output_size < original_size and output_size < MAX_TELEGRAM_SIZE:
                if status_msg:
                    reduction = (1 - output_size / original_size) * 100
                    await status_msg.edit_text(
                        f"✅ Video compressed successfully!\n"
                        f"📉 Size reduced by {reduction:.1f}%\n"
                        f"Original: {original_size / (1024*1024*1024):.2f} GB\n"
                        f"Compressed: {output_size / (1024*1024*1024):.2f} GB"
                    )
                return True
            else:
                if output_size >= MAX_TELEGRAM_SIZE:
                    if status_msg:
                        await status_msg.edit_text(f"🔄 File still too large, trying higher compression...")
                    cmd[7] = "28"
                    
                    proc2 = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc2.wait()
                    
                    if proc2.returncode == 0 and os.path.exists(output_path):
                        output_size2 = os.path.getsize(output_path)
                        if output_size2 < MAX_TELEGRAM_SIZE:
                            return True
                
                return False
        else:
            print(f"FFmpeg failed: {stderr.decode() if stderr else 'Unknown error'}")
            return False
            
    except Exception as e:
        print(f"Video compression error: {e}")
        return False

@Client.on_message(filters.regex(r"https?://(www\.)?(dropbox\.com|.*\.dl\.dropboxusercontent\.com)/.*") & filters.user(OWNER_ID))
async def dropbox_handler(client: Client, message: Message):
    url = message.text.strip()
    
    import re
    if "dropbox.com" in url or "dropboxusercontent.com" in url:
        url = re.sub(r'[?&]dl=[01]', '', url)
        if '?' in url:
            url += '&dl=1'
        else:
            url += '?dl=1'

    status_msg = await message.reply_text("🚀 Initializing download...")
    
    temp_dir = f"downloads/{message.id}"
    os.makedirs(temp_dir, exist_ok=True)
    zip_path = f"{temp_dir}/download.zip"
    extract_path = f"{temp_dir}/extracted"

    try:
        from utils.downloader import SmartDownloader
        
        async def download_progress(current, total):
             if not hasattr(download_progress, 'prog'):
                 download_progress.prog = Progress(status_msg, total, "Downloading")
             await download_progress.prog.update(current)
        
        downloader = SmartDownloader(
            url, 
            zip_path, 
            concurrency=16,
            progress_callback=download_progress
        )
        
        await status_msg.edit_text("⬇️ Downloading with Aria2c...")
        await downloader.download()
        await downloader.close()
        
        await status_msg.edit_text("📦 Extracting files...")
        async def extract_progress(current, total):
            if not hasattr(extract_progress, 'prog'):
                extract_progress.prog = Progress(status_msg, total, "Extracting")
            await extract_progress.prog.update(current)

        await extract_zip(zip_path, extract_path, progress_callback=extract_progress)
        
        await status_msg.edit_text("🔍 Scanning files...")

        files = []
        for root, dirs, filenames in os.walk(extract_path):
            for filename in filenames:
                if filename.lower().endswith('.json'):
                    continue
                files.append(os.path.join(root, filename))

        total_files = len(files)
        if total_files == 0:
            await status_msg.edit_text("⚠️ No media files found in archive.")
            return
            
        uploaded = 0
        compressed_count = 0
        upload_prog = Progress(status_msg, total_files, "Processing & Uploading")

        for i, file_path in enumerate(files):
            filename = os.path.basename(file_path)
            ext = os.path.splitext(filename)[1].lower()
            file_size = os.path.getsize(file_path)
            
            upload_path = file_path
            caption = f"📁 Backup: {filename}"
            compressed = False
            
            if ext in IMAGE_FORMATS:
                target_ext = ext
                if ext in ['.heic', '.heif', '.tiff', '.tif', '.bmp']:
                    target_ext = '.jpg'
                
                compressed_path = f"{file_path}_compressed{target_ext}"
                
                await status_msg.edit_text(
                    f"🖼️ Processing image ({i+1}/{total_files})\n"
                    f"📄 {filename}\n"
                    f"📊 Size: {file_size / (1024*1024):.2f} MB"
                )
                
                if await compress_image(file_path, compressed_path):
                    compressed_size = os.path.getsize(compressed_path)
                    should_use_compressed = False
                    if ext in ['.heic', '.heif', '.tiff', '.tif', '.bmp']:
                        should_use_compressed = True
                    elif compressed_size < file_size * 0.98:
                        should_use_compressed = True
                        
                    if should_use_compressed:
                        upload_path = compressed_path
                        compressed = True
                        compressed_count += 1
                        caption = f"🖼️ Backup (Optimized): {os.path.splitext(filename)[0]}{target_ext}"
            
            elif ext in VIDEO_FORMATS:
                if file_size > MAX_TELEGRAM_SIZE:
                    compressed_path = f"{file_path}_compressed.mp4"
                    
                    await status_msg.edit_text(
                        f"🎬 Compressing video ({i+1}/{total_files})\n"
                        f"📄 {filename}\n"
                        f"📊 Original: {file_size / (1024*1024*1024):.2f} GB"
                    )
                    
                    if await compress_video_h265(file_path, compressed_path, status_msg):
                        compressed_size = os.path.getsize(compressed_path)
                        
                        if compressed_size < MAX_TELEGRAM_SIZE:
                            upload_path = compressed_path
                            compressed = True
                            compressed_count += 1
                            caption = f"🎬 Backup (H.265 Compressed): {os.path.basename(compressed_path)}"
                            ext = '.mp4'
                        else:
                            await status_msg.edit_text(
                                f"⚠️ Video masih terlalu besar setelah compress: {filename}\n"
                                f"Skipping file ini..."
                            )
                            if os.path.exists(compressed_path):
                                os.remove(compressed_path)
                            continue
                    else:
                        await status_msg.edit_text(
                            f"❌ Compression gagal: {filename}\n"
                            f"Skipping file ini..."
                        )
                        continue

            max_retries = 30
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    if ext in IMAGE_FORMATS:
                        await client.send_photo(
                            chat_id=DUMP_CHAT_ID,
                            photo=upload_path,
                            caption=caption,
                            progress=lambda current, total: None
                        )
                    elif ext in VIDEO_FORMATS:
                        await client.send_video(
                            chat_id=DUMP_CHAT_ID,
                            video=upload_path,
                            caption=caption,
                            supports_streaming=True,
                            progress=lambda current, total: None
                        )
                    else:
                        await client.send_document(
                            chat_id=DUMP_CHAT_ID,
                            document=upload_path,
                            caption=caption,
                            progress=lambda current, total: None
                        )
                    
                    uploaded += 1
                    await upload_prog.update(uploaded)
                    break
                    
                except FloodWait as e:
                    print(f"⏳ FloodWait: Sleeping {e.value}s...")
                    await asyncio.sleep(e.value)
                    retry_count += 1
                    
                except Exception as e:
                    print(f"❌ Upload error for {filename}: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"⚠️ Skipping {filename} after {max_retries} retries")
                        break
                    await asyncio.sleep(2)
            
            if compressed and os.path.exists(upload_path) and upload_path != file_path:
                try:
                    os.remove(upload_path)
                except Exception as e:
                    print(f"Cleanup error: {e}")

        await status_msg.edit_text(
            f"✅ Upload Complete!\n\n"
            f"📊 Statistics:\n"
            f"• Total files: {total_files}\n"
            f"• Uploaded: {uploaded}\n"
            f"• Compressed: {compressed_count}\n"
            f"• Success rate: {(uploaded/total_files)*100:.1f}%"
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")
        print(f"Error processing dropbox link: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        try:
            shutil.rmtree(temp_dir)
            print(f"🧹 Cleaned up {temp_dir}")
        except Exception as e:
            print(f"⚠️ Cleanup failed for {temp_dir}: {e}")
