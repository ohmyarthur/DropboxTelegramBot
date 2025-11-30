import asyncio
import os
import time
from utils.progress import Progress

class SmartDownloader:
    def __init__(self, url, dest_path, progress_callback=None, concurrency=16, chunk_size=None):
        self.url = url
        self.dest_path = dest_path
        self.progress_callback = progress_callback
        self.concurrency = concurrency
        self.total_size = 0
        self.downloaded = 0
        self.process = None

    async def initialize(self):
        pass

    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                self.process.terminate()
                await self.process.wait()
            except ProcessLookupError:
                pass

    async def download(self):
        start_time = time.time()
        
        cmd = [
            "aria2c",
            "--max-connection-per-server", str(self.concurrency),
            "--split", str(self.concurrency),
            "--min-split-size", "1M",
            "--out", os.path.basename(self.dest_path),
            "--dir", os.path.dirname(self.dest_path),
            "--file-allocation=none",
            "--summary-interval=1",
            "--quiet=false",
            self.url
        ]
        
        print(f"Starting aria2c download: {' '.join(cmd)}")
        
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        while True:
            line = await self.process.stdout.readline()
            if not line:
                break
                
            line = line.decode('utf-8').strip()
            if line:
                if line.startswith("[#") and "/" in line and "(" in line:
                    try:
                        parts = line.split()
                        for part in parts:
                            if "/" in part and "(" in part:
                                size_part = part.split("(")[0]
                                current_str, total_str = size_part.split("/")
                                pass
                    except Exception:
                        pass
            
            if self.process.stdout.at_eof():
                break

        await self.process.wait()
        
        if self.process.returncode != 0:
            stderr = await self.process.stderr.read()
            raise Exception(f"Aria2c failed with code {self.process.returncode}: {stderr.decode('utf-8')}")
            
        if os.path.exists(self.dest_path):
            self.total_size = os.path.getsize(self.dest_path)
            self.downloaded = self.total_size
            if self.progress_callback:
                await self.progress_callback(self.total_size)
        else:
            raise Exception("Download finished but file not found")

        download_time = time.time() - start_time
        speed = (self.total_size / (1024 * 1024)) / download_time if download_time > 0 else 0
        print(f"Aria2c download completed in {download_time:.2f}s ({speed:.2f} MB/s)")
        
        return self.dest_path
