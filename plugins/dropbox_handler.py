import os
import shutil
import time
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
import asyncio
from config import DUMP_CHAT_ID, OWNER_ID
from utils.aerofs_helper import write_stream_to_file
from utils.zip_helper import extract_zip
from utils.progress import Progress
from utils.session_manager import session_manager
from PIL import Image, ImageOps
import pillow_heif

pillow_heif.register_heif_opener()

VIDEO_FORMATS = ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.3gp', '.ts', '.mpg', '.mpeg', '.m2ts', '.mts']
IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.webp', '.tiff', '.tif', '.bmp', '.gif']
HEIF_FORMATS = ['.heic', '.heif']
GIF_FORMATS = ['.gif']
DOCUMENT_FORMATS = ['.pdf', '.doc', '.docx', '.txt', '.zip', '.rar', '.7z']
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
        
        if file_size < 500 * 1024:
            img.save(output_path, 'PNG', optimize=True)
        else:
            save_params = {
                'format': 'JPEG',
                'quality': max_quality,
                'optimize': True,
                'progressive': True,
                'subsampling': 0,
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

async def convert_heic_to_jpeg(input_path: str, output_path: str, quality: int = 95) -> bool:
    try:
        img = Image.open(input_path)
        exif_data = img.info.get('exif', None)

        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        else:
            img = img.convert('RGB')

        save_params = {
            'format': 'JPEG',
            'quality': quality,
            'optimize': True,
            'progressive': True,
            'subsampling': 0,
        }
        if exif_data:
            save_params['exif'] = exif_data
        img.save(output_path, **save_params)
        return os.path.exists(output_path)
    except Exception as e:
        print(f"HEIC convert error: {e}")
        return False

async def ensure_valid_photo_dimensions(input_path: str) -> str:
    try:
        img = Image.open(input_path)
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        width, height = img.size
        if width <= 0 or height <= 0:
            return input_path

        MAX_SIDE = 10000
        MAX_PIXELS = 40_000_000
        scale = 1.0

        if width > MAX_SIDE or height > MAX_SIDE:
            scale = min(scale, MAX_SIDE / float(max(width, height)))

        if width * height > MAX_PIXELS:
            pixel_scale = (MAX_PIXELS / float(width * height)) ** 0.5
            if pixel_scale < scale:
                scale = pixel_scale

        if scale >= 1.0:
            return input_path

        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        img = img.resize((new_width, new_height), Image.LANCZOS)

        base, _ = os.path.splitext(input_path)
        output_path = f"{base}_tgfixed.jpg"

        exif_data = img.info.get('exif', None)
        save_params = {
            'format': 'JPEG',
            'quality': 95,
            'optimize': True,
            'progressive': True,
            'subsampling': 0,
        }
        if exif_data:
            save_params['exif'] = exif_data
        img.save(output_path, **save_params)

        if os.path.exists(output_path):
            return output_path
        return input_path
    except Exception as e:
        print(f"Photo dimension fix error: {e}")
        return input_path

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

def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Select Media Types", callback_data=f"media_menu:{user_id}")],
        [InlineKeyboardButton("📤 Select Dump Channel", callback_data=f"channel_menu:{user_id}")],
        [InlineKeyboardButton("⚙️ Settings Summary", callback_data=f"settings:{user_id}")],
        [InlineKeyboardButton("✅ Start Download", callback_data=f"download_start:{user_id}")]
    ])

def get_media_selection_keyboard(user_id: int) -> InlineKeyboardMarkup:
    photos_enabled = session_manager.is_media_type_enabled(user_id, 'photos')
    videos_enabled = session_manager.is_media_type_enabled(user_id, 'videos')
    gifs_enabled = session_manager.is_media_type_enabled(user_id, 'gifs')
    docs_enabled = session_manager.is_media_type_enabled(user_id, 'documents')
    other_enabled = session_manager.is_media_type_enabled(user_id, 'other')
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'✅' if photos_enabled else '❌'} Photos", 
            callback_data=f"media_toggle:photos:{user_id}"
        )],
        [InlineKeyboardButton(
            f"{'✅' if videos_enabled else '❌'} Videos", 
            callback_data=f"media_toggle:videos:{user_id}"
        )],
        [InlineKeyboardButton(
            f"{'✅' if gifs_enabled else '❌'} GIFs", 
            callback_data=f"media_toggle:gifs:{user_id}"
        )],
        [InlineKeyboardButton(
            f"{'✅' if docs_enabled else '❌'} Documents", 
            callback_data=f"media_toggle:documents:{user_id}"
        )],
        [InlineKeyboardButton(
            f"{'✅' if other_enabled else '❌'} Other Files", 
            callback_data=f"media_toggle:other:{user_id}"
        )],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data=f"main_menu:{user_id}")]
    ])

def get_channel_selection_keyboard(user_id: int) -> InlineKeyboardMarkup:
    current_channel = session_manager.get_dump_channel(user_id)
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📍 Use Default Channel", callback_data=f"channel_default:{user_id}")],
        [InlineKeyboardButton("✏️ Enter Custom Channel ID", callback_data=f"channel_custom:{user_id}")],
        [InlineKeyboardButton(f"Current: {current_channel}", callback_data=f"noop:{user_id}")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data=f"main_menu:{user_id}")]
    ])

def should_process_file(filename: str, selected_types: set, ext: str) -> bool:
    ext_lower = ext.lower()
    
    if 'photos' in selected_types and (ext_lower in IMAGE_FORMATS or ext_lower in HEIF_FORMATS):
        if ext_lower in GIF_FORMATS and 'gifs' not in selected_types:
            return False
        return True
    
    if 'videos' in selected_types and ext_lower in VIDEO_FORMATS:
        return True
    
    if 'gifs' in selected_types and ext_lower in GIF_FORMATS:
        return True
    
    if 'documents' in selected_types and ext_lower in DOCUMENT_FORMATS:
        return True
    
    if 'other' in selected_types:
        if (ext_lower not in IMAGE_FORMATS and ext_lower not in HEIF_FORMATS and
            ext_lower not in VIDEO_FORMATS and ext_lower not in DOCUMENT_FORMATS):
            return True
    
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

    session_manager.create_session(message.from_user.id, url)
    
    await message.reply_text(
        "🎯 **Dropbox Download Configuration**\n\n"
        f"📎 Link: `{url[:50]}...`\n\n"
        "Please select your preferences:",
        reply_markup=get_main_menu_keyboard(message.from_user.id)
    )

@Client.on_callback_query(filters.regex(r"^main_menu:") & filters.user(OWNER_ID))
async def main_menu_callback(client: Client, callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ This is not your session!", show_alert=True)
        return
    
    session = session_manager.get_session(user_id)
    if not session:
        await callback.answer("❌ Session expired. Please send the link again.", show_alert=True)
        return
    
    url = session['url']
    await callback.edit_message_text(
        "🎯 **Dropbox Download Configuration**\n\n"
        f"📎 Link: `{url[:50]}...`\n\n"
        "Please select your preferences:",
        reply_markup=get_main_menu_keyboard(user_id)
    )
    await callback.answer()

@Client.on_callback_query(filters.regex(r"^media_menu:") & filters.user(OWNER_ID))
async def media_menu_callback(client: Client, callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ This is not your session!", show_alert=True)
        return
    
    await callback.edit_message_text(
        "📂 **Select Media Types to Download**\n\n"
        "Toggle the types you want to download:",
        reply_markup=get_media_selection_keyboard(user_id)
    )
    await callback.answer()

@Client.on_callback_query(filters.regex(r"^media_toggle:") & filters.user(OWNER_ID))
async def media_toggle_callback(client: Client, callback: CallbackQuery):
    parts = callback.data.split(":")
    media_type = parts[1]
    user_id = int(parts[2])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ This is not your session!", show_alert=True)
        return
    
    new_state = session_manager.toggle_media_type(user_id, media_type)
    
    await callback.edit_message_reply_markup(
        reply_markup=get_media_selection_keyboard(user_id)
    )
    
    status = "enabled" if new_state else "disabled"
    await callback.answer(f"✓ {media_type.capitalize()} {status}")

@Client.on_callback_query(filters.regex(r"^channel_menu:") & filters.user(OWNER_ID))
async def channel_menu_callback(client: Client, callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ This is not your session!", show_alert=True)
        return
    
    await callback.edit_message_text(
        "📤 **Select Dump Channel**\n\n"
        "Choose where to upload the files:",
        reply_markup=get_channel_selection_keyboard(user_id)
    )
    await callback.answer()

@Client.on_callback_query(filters.regex(r"^channel_default:") & filters.user(OWNER_ID))
async def channel_default_callback(client: Client, callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ This is not your session!", show_alert=True)
        return
    
    session_manager.set_dump_channel(user_id, DUMP_CHAT_ID)
    
    await callback.edit_message_reply_markup(
        reply_markup=get_channel_selection_keyboard(user_id)
    )
    await callback.answer(f"✓ Set to default channel: {DUMP_CHAT_ID}")

@Client.on_callback_query(filters.regex(r"^channel_custom:") & filters.user(OWNER_ID))
async def channel_custom_callback(client: Client, callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ This is not your session!", show_alert=True)
        return
    
    session_manager.set_awaiting_channel_input(user_id, True)
    
    await callback.answer("Please send the channel ID (e.g., -1001234567890)", show_alert=True)
    await callback.message.reply_text(
        "✏️ **Enter Custom Channel ID**\n\n"
        "Please send the channel ID in the format:\n"
        "`-1001234567890`\n\n"
        "Or send /cancel to go back."
    )

@Client.on_message(filters.text & filters.user(OWNER_ID) & ~filters.command("start"))
async def handle_channel_input(client: Client, message: Message):
    user_id = message.from_user.id
    
    if not session_manager.is_awaiting_channel_input(user_id):
        return
    
    if message.text == "/cancel":
        session_manager.set_awaiting_channel_input(user_id, False)
        await message.reply_text(
            "❌ Cancelled.",
            reply_markup=get_main_menu_keyboard(user_id)
        )
        return
    
    try:
        channel_id = int(message.text.strip())
        session_manager.set_dump_channel(user_id, channel_id)
        session_manager.set_awaiting_channel_input(user_id, False)
        
        await message.reply_text(
            f"✅ Dump channel set to: `{channel_id}`",
            reply_markup=get_main_menu_keyboard(user_id)
        )
    except ValueError:
        await message.reply_text(
            "❌ Invalid channel ID. Please send a valid number like `-1001234567890`\n\n"
            "Or send /cancel to go back."
        )

@Client.on_callback_query(filters.regex(r"^settings:") & filters.user(OWNER_ID))
async def settings_callback(client: Client, callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ This is not your session!", show_alert=True)
        return
    
    session = session_manager.get_session(user_id)
    if not session:
        await callback.answer("❌ Session expired!", show_alert=True)
        return
    
    media_types = session['media_types']
    dump_channel = session['dump_channel']
    url = session['url']
    
    media_list = []
    if 'photos' in media_types:
        media_list.append("✅ Photos")
    if 'videos' in media_types:
        media_list.append("✅ Videos")
    if 'gifs' in media_types:
        media_list.append("✅ GIFs")
    if 'documents' in media_types:
        media_list.append("✅ Documents")
    if 'other' in media_types:
        media_list.append("✅ Other Files")
    
    if not media_list:
        media_list.append("❌ No media types selected!")
    
    settings_text = (
        "⚙️ **Current Settings**\n\n"
        f"📎 **URL:** `{url[:40]}...`\n\n"
        f"📂 **Media Types:**\n" + "\n".join(media_list) + "\n\n"
        f"📤 **Dump Channel:** `{dump_channel}`"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data=f"main_menu:{user_id}")]
    ])
    
    await callback.edit_message_text(settings_text, reply_markup=keyboard)
    await callback.answer()

@Client.on_callback_query(filters.regex(r"^download_start:") & filters.user(OWNER_ID))
async def download_start_callback(client: Client, callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ This is not your session!", show_alert=True)
        return
    
    session = session_manager.get_session(user_id)
    if not session:
        await callback.answer("❌ Session expired!", show_alert=True)
        return
    
    media_types = session['media_types']
    if not media_types:
        await callback.answer("❌ Please select at least one media type!", show_alert=True)
        return
    
    url = session['url']
    dump_channel = session['dump_channel']
    
    await callback.answer("🚀 Starting download...")
    
    await callback.edit_message_text("🚀 Initializing download...")
    
    await process_download(client, callback.message, url, dump_channel, media_types, user_id)

async def process_download(client: Client, status_msg: Message, url: str, dump_channel: int, media_types: set, user_id: int):
    temp_dir = f"downloads/{status_msg.id}"
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
                
                file_path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()
                
                if should_process_file(filename, media_types, ext):
                    files.append(file_path)

        total_files = len(files)
        if total_files == 0:
            await status_msg.edit_text("⚠️ No matching media files found in archive.")
            session_manager.delete_session(user_id)
            return
            
        uploaded = 0
        compressed_count = 0
        upload_prog = Progress(status_msg, total_files, "Processing & Uploading")

        pending_photos = []

        async def flush_album():
            nonlocal pending_photos, uploaded
            if not pending_photos:
                return

            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    media_group = []
                    for idx, item in enumerate(pending_photos):
                        media_group.append(
                            InputMediaPhoto(
                                media=item["upload_path"],
                                caption=item["caption"] if idx == 0 else None
                            )
                        )

                    await client.send_media_group(
                        chat_id=dump_channel,
                        media=media_group
                    )

                    uploaded += len(pending_photos)
                    await upload_prog.update(uploaded)
                    break

                except FloodWait as e:
                    print(f"⏳ FloodWait (album): Sleeping {e.value}s...")
                    await asyncio.sleep(e.value)
                    retry_count += 1

                except Exception as e:
                    print(f"❌ Album upload error: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"⚠️ Skipping album after {max_retries} retries")
                        break
                    await asyncio.sleep(2)

            for item in pending_photos:
                if item["compressed"] and os.path.exists(item["upload_path"]) and item["upload_path"] != item["file_path"]:
                    try:
                        os.remove(item["upload_path"])
                    except Exception as e:
                        print(f"Cleanup error: {e}")

            pending_photos = []

        for i, file_path in enumerate(files):
            filename = os.path.basename(file_path)
            ext = os.path.splitext(filename)[1].lower()
            file_size = os.path.getsize(file_path)
            
            upload_path = file_path
            caption = f"📁 Backup: {filename}"
            compressed = False
            
            if ext in IMAGE_FORMATS or ext in HEIF_FORMATS:
                await status_msg.edit_text(
                    f"🖼️ Processing image ({i+1}/{total_files})\n"
                    f"📄 {filename}\n"
                    f"📊 Size: {file_size / (1024*1024):.2f} MB"
                )
                
                if ext in HEIF_FORMATS:
                    target_ext = '.jpg'
                    converted_path = f"{file_path}_converted{target_ext}"
                    if await convert_heic_to_jpeg(file_path, converted_path):
                        upload_path = converted_path
                        compressed = True
                        compressed_count += 1
                        caption = f"🖼️ Backup: {os.path.splitext(filename)[0]}{target_ext}"
                        ext = target_ext
                    else:
                        caption = f"📁 Backup (Original HEIC): {filename}"

                if ext in IMAGE_FORMATS:
                    fixed_path = await ensure_valid_photo_dimensions(upload_path)
                    if fixed_path != upload_path:
                        upload_path = fixed_path
                        compressed = True
                        compressed_count += 1
                        ext = os.path.splitext(upload_path)[1].lower()
            
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

            if ext in IMAGE_FORMATS:
                pending_photos.append({
                    "file_path": file_path,
                    "upload_path": upload_path,
                    "caption": caption,
                    "compressed": compressed,
                })

                if len(pending_photos) >= 10:
                    await flush_album()

                continue

            if pending_photos:
                await flush_album()

            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    if ext in VIDEO_FORMATS:
                        await client.send_video(
                            chat_id=dump_channel,
                            video=upload_path,
                            caption=caption,
                            supports_streaming=True,
                            progress=lambda current, total: None
                        )
                    else:
                        await client.send_document(
                            chat_id=dump_channel,
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

        if pending_photos:
            await flush_album()

        await status_msg.edit_text(
            f"✅ Upload Complete!\n\n"
            f"📊 Statistics:\n"
            f"• Total files: {total_files}\n"
            f"• Uploaded: {uploaded}\n"
            f"• Compressed: {compressed_count}\n"
            f"• Success rate: {(uploaded/total_files)*100:.1f}%"
        )
        
        session_manager.delete_session(user_id)

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")
        print(f"Error processing dropbox link: {e}")
        import traceback
        traceback.print_exc()
        session_manager.delete_session(user_id)
        
    finally:
        try:
            shutil.rmtree(temp_dir)
            print(f"🧹 Cleaned up {temp_dir}")
        except Exception as e:
            print(f"⚠️ Cleanup failed for {temp_dir}: {e}")

@Client.on_callback_query(filters.regex(r"^noop:"))
async def noop_callback(client: Client, callback: CallbackQuery):
    await callback.answer()