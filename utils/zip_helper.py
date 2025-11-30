import zipfile
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor()

def _extract_zip_sync(zip_path, extract_to):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    return os.listdir(extract_to)

async def extract_zip(zip_path, extract_to):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, _extract_zip_sync, zip_path, extract_to)
