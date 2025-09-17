import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ActiveSession:
    dialog_id: str
    gemini_chat: Any
    last_activity_at: float
    last_image_meta: Dict[str, Any]
    message_seq: int = 0


class SessionManager:
    def __init__(self, idle_timeout_minutes: int) -> None:
        self._sessions: Dict[int, ActiveSession] = {}
        self._idle_seconds = idle_timeout_minutes * 60

    def get(self, chat_id: int) -> Optional[ActiveSession]:
        s = self._sessions.get(chat_id)
        if not s:
            return None
        if time.time() - s.last_activity_at > self._idle_seconds:
            # idle timeout
            self._sessions.pop(chat_id, None)
            return None
        return s

    def set(self, chat_id: int, session: ActiveSession) -> None:
        self._sessions[chat_id] = session

    def clear(self, chat_id: int) -> None:
        self._sessions.pop(chat_id, None)


