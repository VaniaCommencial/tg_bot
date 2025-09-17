import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DialogIndexEntry:
    dialog_id: str
    started_at: float
    closed_at: Optional[float]
    title: str
    has_image: bool
    message_count: int
    tokens_estimate: int
    warning_shown: bool


@dataclass
class UserProfile:
    chat_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    first_seen: float
    last_seen: float
    language: str
    dialogs_index: List[DialogIndexEntry]
    stats: Dict[str, Any]


class JsonStore:
    def __init__(self, base_dir: str) -> None:
        self.base = Path(base_dir)
        self.users_dir = self.base / "users"
        self.dialogs_dir = self.base / "dialogs"
        self.tmp_dir = self.base / "tmp"
        for d in (self.users_dir, self.dialogs_dir, self.tmp_dir):
            d.mkdir(parents=True, exist_ok=True)

    def _user_path(self, chat_id: int) -> Path:
        return self.users_dir / f"{chat_id}.json"

    def _dialog_path(self, chat_id: int, dialog_id: str) -> Path:
        ddir = self.dialogs_dir / str(chat_id)
        ddir.mkdir(parents=True, exist_ok=True)
        return ddir / f"{dialog_id}.json"

    # Atomic write helper
    def _atomic_write(self, path: Path, content: Dict[str, Any]) -> None:
        tmp = self.tmp_dir / f"{path.name}.{int(time.time()*1000)}.tmp"
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def load_user(self, chat_id: int) -> Optional[Dict[str, Any]]:
        p = self._user_path(chat_id)
        if not p.exists():
            return None
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_user(self, user: Dict[str, Any]) -> None:
        p = self._user_path(user["chat_id"])
        self._atomic_write(p, user)

    def init_user_if_needed(
        self,
        chat_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        language: str = "ru",
    ) -> Dict[str, Any]:
        now = time.time()
        u = self.load_user(chat_id)
        if u is None:
            u = {
                "chat_id": chat_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "first_seen": now,
                "last_seen": now,
                "language": language,
                "dialogs_index": [],
                "stats": {
                    "total_requests": 0,
                    "total_dialogs": 0,
                    "last_active_at": now,
                },
            }
        else:
            u["last_seen"] = now
            u["stats"]["last_active_at"] = now
        self.save_user(u)
        return u

    def add_dialog_index_entry(self, chat_id: int, entry: DialogIndexEntry) -> None:
        u = self.load_user(chat_id)
        if u is None:
            raise RuntimeError("User must be initialized before adding dialog entry")
        idx = u.get("dialogs_index", [])
        idx.append(asdict(entry))
        u["dialogs_index"] = idx
        u["stats"]["total_dialogs"] = u["stats"].get("total_dialogs", 0) + 1
        self.save_user(u)

    def update_dialog_index_entry(self, chat_id: int, dialog_id: str, **updates: Any) -> None:
        u = self.load_user(chat_id)
        if u is None:
            return
        idx = u.get("dialogs_index", [])
        for e in idx:
            if e.get("dialog_id") == dialog_id:
                e.update(updates)
                break
        self.save_user(u)

    def list_dialogs(self, chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        u = self.load_user(chat_id)
        if u is None:
            return []
        idx = list(u.get("dialogs_index", []))
        idx.sort(key=lambda e: e.get("started_at", 0), reverse=True)
        return idx[:limit]

    def open_dialog(
        self,
        chat_id: int,
        dialog_id: str,
        model: str,
        image_meta: Dict[str, Any],
        caption_text: Optional[str],
    ) -> None:
        path = self._dialog_path(chat_id, dialog_id)
        now = time.time()
        data = {
            "dialog_id": dialog_id,
            "chat_id": chat_id,
            "started_at": now,
            "closed_at": None,
            "model": model,
            "language": "ru",
            "image_meta": {**image_meta, "caption_text": caption_text, "received_at": now},
            "messages": [],
            "summary": "",
            "indices": {"keywords": [], "dates": [], "entities": []},
            "limits": {"max_messages": 500},
        }
        self._atomic_write(path, data)

    def append_message(
        self,
        chat_id: int,
        dialog_id: str,
        message: Dict[str, Any],
    ) -> None:
        path = self._dialog_path(chat_id, dialog_id)
        if not path.exists():
            raise FileNotFoundError(str(path))
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        msgs = data.get("messages", [])
        msgs.append(message)
        data["messages"] = msgs
        self._atomic_write(path, data)
        # update user stats message count
        u = self.load_user(chat_id)
        if u:
            u.setdefault("stats", {})
            u["stats"]["total_requests"] = u["stats"].get("total_requests", 0) + 1
            self.save_user(u)

    def close_dialog(self, chat_id: int, dialog_id: str) -> None:
        path = self._dialog_path(chat_id, dialog_id)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        data["closed_at"] = time.time()
        self._atomic_write(path, data)

    def get_dialog(self, chat_id: int, dialog_id: str) -> Optional[Dict[str, Any]]:
        path = self._dialog_path(chat_id, dialog_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def delete_dialog(self, chat_id: int, dialog_id: str) -> bool:
        # remove dialog file and index entry
        path = self._dialog_path(chat_id, dialog_id)
        existed = path.exists()
        if existed:
            try:
                path.unlink()
            except Exception:
                existed = False
        u = self.load_user(chat_id)
        if u is not None:
            idx = [e for e in u.get("dialogs_index", []) if e.get("dialog_id") != dialog_id]
            u["dialogs_index"] = idx
            self.save_user(u)
        return existed

    def clear_all_dialogs(self, chat_id: int) -> int:
        # delete all dialogs for user
        ddir = self.dialogs_dir / str(chat_id)
        count = 0
        if ddir.exists():
            for p in ddir.glob("*.json"):
                try:
                    p.unlink()
                    count += 1
                except Exception:
                    pass
        u = self.load_user(chat_id)
        if u is not None:
            u["dialogs_index"] = []
            self.save_user(u)
        return count

    def prune_old(self, days: int) -> int:
        # remove dialogs older than days across all users
        cutoff = time.time() - days * 86400
        removed = 0
        for chat_dir in self.dialogs_dir.glob("*"):
            if not chat_dir.is_dir():
                continue
            chat_id = int(chat_dir.name) if chat_dir.name.isdigit() else None
            for p in chat_dir.glob("*.json"):
                try:
                    with p.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    started = float(data.get("started_at", 0))
                except Exception:
                    started = 0
                if started and started < cutoff:
                    try:
                        dialog_id = data.get("dialog_id")
                        p.unlink()
                        removed += 1
                        if chat_id is not None and dialog_id:
                            u = self.load_user(chat_id)
                            if u:
                                idx = [e for e in u.get("dialogs_index", []) if e.get("dialog_id") != dialog_id]
                                u["dialogs_index"] = idx
                                self.save_user(u)
                    except Exception:
                        pass
        return removed

    def user_stats(self, chat_id: int) -> Dict[str, Any]:
        u = self.load_user(chat_id) or {}
        idx = u.get("dialogs_index", [])
        return {
            "dialogs": len(idx),
            "requests": (u.get("stats", {}).get("total_requests", 0)),
            "last_active_at": u.get("stats", {}).get("last_active_at"),
        }

    def global_stats(self) -> Dict[str, Any]:
        users = list(self.users_dir.glob("*.json"))
        total_users = len(users)
        total_dialogs = 0
        total_requests = 0
        for p in users:
            try:
                with p.open("r", encoding="utf-8") as f:
                    u = json.load(f)
                total_dialogs += len(u.get("dialogs_index", []))
                total_requests += u.get("stats", {}).get("total_requests", 0)
            except Exception:
                pass
        return {
            "users": total_users,
            "dialogs": total_dialogs,
            "requests": total_requests,
        }


