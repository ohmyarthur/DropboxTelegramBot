import asyncio
import aiohttp
import aerofs
import os
import gzip

class SmartDownloader:
    def __init__(self, url, dest_path, progress_callback=None, concurrency=16, chunk_size=1024*1024):
        self.url = url
        self.dest_path = dest_path
        self.progress_callback = progress_callback
        self.concurrency = concurrency
        self.chunk_size = chunk_size
        self.total_size = 0
        self.downloaded = 0
        self._lock = asyncio.Lock()

    async def _get_size(self):
        async with aiohttp.ClientSession() as session:
            async with session.head(self.url, allow_redirects=True) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get file info: {response.status}")
                return int(response.headers.get('Content-Length', 0))

    async def _download_chunk(self, session, start, end):
        headers = {
            'Range': f'bytes={start}-{end}',
            'Accept-Encoding': 'identity',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        async with session.get(self.url, headers=headers) as response:
            if response.status not in (200, 206):
                raise Exception(f"Failed to download chunk: {response.status}")
            
            async with aerofs.open(self.dest_path, 'r+b') as f:
                await f.seek(start)
                
                async for data in response.content.iter_chunked(self.chunk_size):
                    if data.startswith(b'\x1f\x8b'):
                        try:
                            data = gzip.decompress(data)
                        except:
                            pass
                    
                    await f.write(data)
                    
                    async with self._lock:
                        self.downloaded += len(data)
                        if self.progress_callback:
                            await self.progress_callback(self.downloaded)

    async def download(self):
        try:
            await self._download_multi_stream()
        except Exception as e:
            print(f"Multi-stream download failed: {e}")
            print("Falling back to simple download...")
            await self._download_simple()
        
        return self.dest_path

    async def _download_multi_stream(self):
        self.total_size = await self._get_size()
        
        async with aerofs.open(self.dest_path, 'wb') as f:
            await f.truncate(self.total_size)

        chunk_size = self.total_size // self.concurrency
        tasks = []
        
        async with aiohttp.ClientSession() as session:
            for i in range(self.concurrency):
                start = i * chunk_size
                end = start + chunk_size - 1 if i < self.concurrency - 1 else self.total_size - 1
                tasks.append(self._download_chunk(session, start, end))
            
            await asyncio.gather(*tasks)

    async def _download_simple(self):
        """Fallback simple download method"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Encoding': 'identity'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download: {response.status}")
                
                self.total_size = int(response.headers.get('Content-Length', 0))
                self.downloaded = 0
                
                async with aerofs.open(self.dest_path, 'wb') as f:
                    async for data in response.content.iter_chunked(self.chunk_size):
                        # Check if data is gzip compressed and decompress if needed
                        if data.startswith(b'\x1f\x8b'):
                            try:
                                data = gzip.decompress(data)
                            except:
                                pass  # If decompression fails, use original data
                        
                        await f.write(data)
                        self.downloaded += len(data)
                        
                        if self.progress_callback:
                            await self.progress_callback(self.downloaded)
