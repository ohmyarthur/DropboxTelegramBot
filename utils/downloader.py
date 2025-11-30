import asyncio
import os
import time
from utils.progress import Progress
from utils.user_agents import get_random_user_agent

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
        
        user_agent = get_random_user_agent()
        
        cmd = [
            "aria2c",
            "--max-connection-per-server", str(self.concurrency),
            "--split", str(self.concurrency),
            "--min-split-size", "1M",
            "--out", os.path.basename(self.dest_path),
            "--dir", os.path.dirname(self.dest_path) or ".",
            "--file-allocation=none",
            "--summary-interval=1",
            "--console-log-level=warn",
            "--max-tries=5",
            "--retry-wait=3",
            "--timeout=60",
            "--connect-timeout=30",
            "--max-file-not-found=5",
            "--allow-overwrite=true",
            "--auto-file-renaming=false",
            "--continue=true",
            f"--user-agent={user_agent}",
            f"--header=Accept: */*",
            f"--header=Accept-Language: en-US,en;q=0.9",
            f"--header=Accept-Encoding: gzip, deflate, br",
            f"--header=Connection: keep-alive",
            f"--header=Upgrade-Insecure-Requests: 1",
            f"--referer=https://www.dropbox.com/",
            self.url
        ]
        
        print(f"Starting aria2c download with enhanced headers...")
        
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout_lines = []
        stderr_lines = []
        
        async def read_stderr():
            while True:
                line = await self.process.stderr.readline()
                if not line:
                    break
                stderr_lines.append(line.decode('utf-8').strip())
        
        stderr_task = asyncio.create_task(read_stderr())
        
        while True:
            line = await self.process.stdout.readline()
            if not line:
                break
                
            line = line.decode('utf-8').strip()
            if line:
                stdout_lines.append(line)
                if line.startswith("[#") and "/" in line and "(" in line:
                    try:
                        parts = line.split()
                        for part in parts:
                            if "/" in part and "(" in part:
                                size_part = part.split("(")[0]
                                current_str, total_str = size_part.split("/")
                                
                                def parse_aria_size(s):
                                    s = s.upper()
                                    if s.endswith('KIB'): return float(s[:-3]) * 1024
                                    if s.endswith('MIB'): return float(s[:-3]) * 1024**2
                                    if s.endswith('GIB'): return float(s[:-3]) * 1024**3
                                    if s.endswith('TIB'): return float(s[:-3]) * 1024**4
                                    if s.endswith('B'): return float(s[:-1])
                                    return 0.0

                                current = parse_aria_size(current_str)
                                total = parse_aria_size(total_str)
                                
                                if self.progress_callback and total > 0:
                                    await self.progress_callback(current, total)
                    except Exception:
                        pass
            
            if self.process.stdout.at_eof():
                break

        await self.process.wait()
        await stderr_task
        
        if self.process.returncode != 0:
            stderr_output = '\n'.join(stderr_lines[-20:]) if stderr_lines else "No error output"
            stdout_output = '\n'.join(stdout_lines[-20:]) if stdout_lines else "No stdout output"
            error_msg = f"Aria2c failed with code {self.process.returncode}"
            
            if self.process.returncode == 22:
                error_msg += "\nHTTP or URL error - Possible causes:"
                error_msg += "\n- Server rejected the request (403/404/429)"
                error_msg += "\n- Invalid or expired download link"
                error_msg += "\n- Malformed URL or unsupported protocol"
                error_msg += "\n- Network connectivity issues"
            
            error_msg += f"\n\nURL: {self.url}"
            error_msg += f"\n\nRecent stdout output:\n{stdout_output}"
            error_msg += f"\n\nRecent stderr output:\n{stderr_output}"
            raise Exception(error_msg)
            
        if os.path.exists(self.dest_path):
            self.total_size = os.path.getsize(self.dest_path)
            self.downloaded = self.total_size
            if self.progress_callback:
                await self.progress_callback(self.total_size, self.total_size)
        else:
            raise Exception("Download finished but file not found")

        download_time = time.time() - start_time
        speed = (self.total_size / (1024 * 1024)) / download_time if download_time > 0 else 0
        print(f"Aria2c download completed in {download_time:.2f}s ({speed:.2f} MB/s)")
        
        return self.dest_path