import time
import math
from utils.system_stats import get_system_stats

class Progress:
    def __init__(self, message, total_size, action_name):
        self.message = message
        self.total_size = total_size
        self.action_name = action_name
        self.last_update_time = 0
        self.start_time = time.time()
        self.update_interval = 4

    async def update(self, current, force=False):
        now = time.time()
        if not force and (now - self.last_update_time) < self.update_interval:
            return

        self.last_update_time = now
        percentage = (current / self.total_size) * 100 if self.total_size > 0 else 0
        speed = current / (now - self.start_time) if (now - self.start_time) > 0 else 0
        elapsed_time = now - self.start_time
        
        def human_readable_size(size):
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024:
                    return f"{size:.2f} {unit}"
                size /= 1024
            return f"{size:.2f} PB"

        speed_str = f"{human_readable_size(speed)}/s"
        current_str = human_readable_size(current)
        total_str = human_readable_size(self.total_size)
        
        bar_length = 20
        filled_length = int(bar_length * percentage // 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        stats = get_system_stats()
        
        text = (
            f"**{self.action_name}**\n"
            f"[{bar}] {percentage:.1f}%\n"
            f"**Progress:** {current_str} / {total_str}\n"
            f"**Speed:** {speed_str}\n"
            f"**Elapsed:** {elapsed_time:.1f}s\n\n"
            f"**System Stats:**\n`{stats}`"
        )
        
        try:
            await self.message.edit_text(text)
        except Exception:
            pass
