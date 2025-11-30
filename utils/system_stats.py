import psutil
import os

def get_system_stats():
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    ram_percent = ram.percent
    ram_used = ram.used / (1024 ** 3)
    ram_total = ram.total / (1024 ** 3)
    
    return f"CPU: {cpu_percent}% | RAM: {ram_used:.1f}/{ram_total:.1f}GB ({ram_percent}%)"
