import time
from typing import Dict, Set, Optional
from config import DUMP_CHAT_ID

class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, dict] = {}
        self.timeout = 3600
    
    def create_session(self, user_id: int, url: str) -> None:
        self.sessions[user_id] = {
            'url': url,
            'media_types': {'photos', 'videos', 'gifs', 'documents', 'other'},
            'dump_channel': DUMP_CHAT_ID,
            'timestamp': time.time(),
            'awaiting_channel_input': False
        }
    
    def get_session(self, user_id: int) -> Optional[dict]:
        if user_id not in self.sessions:
            return None
        
        session = self.sessions[user_id]
        if time.time() - session['timestamp'] > self.timeout:
            self.delete_session(user_id)
            return None
        
        return session
    
    def update_timestamp(self, user_id: int) -> None:
        if user_id in self.sessions:
            self.sessions[user_id]['timestamp'] = time.time()
    
    def toggle_media_type(self, user_id: int, media_type: str) -> bool:
        session = self.get_session(user_id)
        if not session:
            return False
        
        if media_type in session['media_types']:
            session['media_types'].discard(media_type)
            self.update_timestamp(user_id)
            return False
        else:
            session['media_types'].add(media_type)
            self.update_timestamp(user_id)
            return True
    
    def is_media_type_enabled(self, user_id: int, media_type: str) -> bool:
        session = self.get_session(user_id)
        if not session:
            return False
        return media_type in session['media_types']
    
    def set_dump_channel(self, user_id: int, channel_id: int) -> None:
        session = self.get_session(user_id)
        if session:
            session['dump_channel'] = channel_id
            self.update_timestamp(user_id)
    
    def get_dump_channel(self, user_id: int) -> Optional[int]:
        session = self.get_session(user_id)
        return session['dump_channel'] if session else None
    
    def get_url(self, user_id: int) -> Optional[str]:
        session = self.get_session(user_id)
        return session['url'] if session else None
    
    def get_media_types(self, user_id: int) -> Set[str]:
        session = self.get_session(user_id)
        return session['media_types'] if session else set()
    
    def set_awaiting_channel_input(self, user_id: int, awaiting: bool) -> None:
        session = self.get_session(user_id)
        if session:
            session['awaiting_channel_input'] = awaiting
            self.update_timestamp(user_id)
    
    def is_awaiting_channel_input(self, user_id: int) -> bool:
        session = self.get_session(user_id)
        return session['awaiting_channel_input'] if session else False
    
    def delete_session(self, user_id: int) -> None:
        if user_id in self.sessions:
            del self.sessions[user_id]
    
    def cleanup_expired(self) -> None:
        current_time = time.time()
        expired = [
            user_id for user_id, session in self.sessions.items()
            if current_time - session['timestamp'] > self.timeout
        ]
        for user_id in expired:
            self.delete_session(user_id)

session_manager = SessionManager()
