import aerofs
import os
import asyncio

async def write_stream_to_file(stream, file_path):
    async with aerofs.open(file_path, 'wb') as f:
        async for chunk in stream:
            await f.write(chunk)

async def read_file_as_stream(file_path, chunk_size=1024*1024):
    async with aerofs.open(file_path, 'rb') as f:
        while True:
            chunk = await f.read(chunk_size)
            if not chunk:
                break
            yield chunk

async def get_file_size(file_path):
    return await aerofs.os.path.getsize(file_path)
