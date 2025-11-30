import zipfile
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor()

def _extract_zip_sync(zip_path, extract_to, progress_callback_sync=None):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        total_size = sum((file.file_size for file in zip_ref.infolist()))
        extracted_size = 0
        
        for file in zip_ref.infolist():
            zip_ref.extract(file, extract_to)
            extracted_size += file.file_size
            if progress_callback_sync:
                progress_callback_sync(extracted_size, total_size)
                
    return os.listdir(extract_to)

async def extract_zip(zip_path, extract_to, progress_callback=None):
    loop = asyncio.get_running_loop()
    
    def sync_callback(current, total):
        if progress_callback:
            asyncio.run_coroutine_threadsafe(progress_callback(current, total), loop)

    return await loop.run_in_executor(executor, _extract_zip_sync, zip_path, extract_to, sync_callback)
