import asyncio
import aiohttp
import aerofs
import os
import time
import random
from utils.user_agents import get_random_user_agent

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
        self.max_retries = 3
        self.base_delay = 1.0
        self.session = None
        self.connector = None
        self.user_agent = get_random_user_agent()

    async def initialize(self):
        if self.session:
            return

        self.connector = aiohttp.TCPConnector(
            limit=self.concurrency + 4,
            limit_per_host=self.concurrency,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(total=300, connect=30, sock_read=60)
        self.session = aiohttp.ClientSession(connector=self.connector, timeout=timeout)

        headers = {
            'User-Agent': self.user_agent,
            'Accept-Encoding': 'identity'
        }
        
        async with self.session.head(self.url, headers=headers, allow_redirects=True) as response:
            if response.status != 200:
                raise Exception(f"Failed to get file info: {response.status}")
            self.total_size = int(response.headers.get('Content-Length', 0))

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _download_chunk_with_retry(self, start, end, chunk_index, retry_count=0):
        headers = {
            'Range': f'bytes={start}-{end}',
            'Accept-Encoding': 'identity',
            'User-Agent': self.user_agent
        }
        
        try:
            async with self.session.get(self.url, headers=headers, allow_redirects=True, auto_decompress=False) as response:
                if response.status not in (200, 206):
                    if retry_count < self.max_retries:
                        delay = self.base_delay * (2 ** retry_count) + random.uniform(0, 1)
                        print(f"Chunk {chunk_index} failed (status {response.status}), retrying in {delay:.2f}s...")
                        await asyncio.sleep(delay)
                        return await self._download_chunk_with_retry(start, end, chunk_index, retry_count + 1)
                    else:
                        raise Exception(f"Failed to download chunk {chunk_index} after {self.max_retries} retries: {response.status}")
                
                chunk_data = bytearray()
                async for data in response.content.iter_chunked(self.chunk_size):
                    chunk_data.extend(data)
                
                async with aerofs.open(self.dest_path, 'r+b') as f:
                    await f.seek(start)
                    await f.write(chunk_data)
                    
                    async with self._lock:
                        self.downloaded += len(chunk_data)
                        if self.progress_callback:
                            await self.progress_callback(self.downloaded)
                
                return len(chunk_data)
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if retry_count < self.max_retries:
                delay = self.base_delay * (2 ** retry_count) + random.uniform(0, 1)
                print(f"Chunk {chunk_index} error ({str(e)}), retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)
                return await self._download_chunk_with_retry(start, end, chunk_index, retry_count + 1)
            else:
                raise Exception(f"Failed to download chunk {chunk_index} after {self.max_retries} retries: {str(e)}")

    async def _download_multi_stream(self):
        if not self.session:
            await self.initialize()

        async with aerofs.open(self.dest_path, 'wb') as f:
            await f.truncate(self.total_size)

        if self.total_size < 10 * 1024 * 1024:
            self.chunk_size = max(256 * 1024, self.total_size // 8)
            actual_concurrency = min(8, self.concurrency)
        elif self.total_size < 100 * 1024 * 1024:
            self.chunk_size = max(512 * 1024, self.total_size // 16)
            actual_concurrency = min(16, self.concurrency)
        else:
            self.chunk_size = max(1024 * 1024, self.total_size // 32)
            actual_concurrency = self.concurrency

        chunk_size = self.total_size // actual_concurrency
        tasks = []
        
        for i in range(actual_concurrency):
            start = i * chunk_size
            end = start + chunk_size - 1 if i < actual_concurrency - 1 else self.total_size - 1
            tasks.append(self._download_chunk_with_retry(start, end, i))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        failed_chunks = [i for i, result in enumerate(results) if isinstance(result, Exception)]
        if failed_chunks:
            raise Exception(f"Failed to download chunks: {failed_chunks}. Errors: {[str(results[i]) for i in failed_chunks]}")

    async def _download_simple(self):
        if not self.session:
            await self.initialize()

        headers = {
            'User-Agent': self.user_agent,
            'Accept-Encoding': 'identity'
        }
        
        for attempt in range(self.max_retries + 1):
            try:
                async with self.session.get(self.url, headers=headers, allow_redirects=True, auto_decompress=False) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to download: {response.status}")
                    
                    self.downloaded = 0
                    
                    async with aerofs.open(self.dest_path, 'wb') as f:
                        async for data in response.content.iter_chunked(self.chunk_size):
                            await f.write(data)
                            self.downloaded += len(data)
                            
                            if self.progress_callback:
                                await self.progress_callback(self.downloaded)
                    
                    return self.dest_path
                        
            except Exception as e:
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt) + random.uniform(0, 2)
                    print(f"Simple download attempt {attempt + 1} failed: {str(e)}, retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                else:
                    raise Exception(f"Simple download failed after {self.max_retries + 1} attempts: {str(e)}")

    async def download(self):
        start_time = time.time()
        
        try:
            if not self.session:
                await self.initialize()

            print(f"Starting multi-stream download with {self.concurrency} connections...")
            await self._download_multi_stream()
            download_time = time.time() - start_time
            speed = (self.total_size / (1024 * 1024)) / download_time if download_time > 0 else 0
            print(f"Multi-stream download completed in {download_time:.2f}s ({speed:.2f} MB/s)")
            
        except Exception as e:
            print(f"Multi-stream download failed: {e}")
            print("Falling back to simple download...")
            
            self.downloaded = 0
            start_time = time.time()
            
            try:
                await self._download_simple()
                download_time = time.time() - start_time
                speed = (self.total_size / (1024 * 1024)) / download_time if download_time > 0 else 0
                print(f"Simple download completed in {download_time:.2f}s ({speed:.2f} MB/s)")
            except Exception as e2:
                raise Exception(f"All download methods failed. Multi-stream: {str(e)}, Simple: {str(e2)}")
        
        return self.dest_path
