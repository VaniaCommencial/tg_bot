import io
import time
from typing import Any, Dict, Optional

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from .storage import JsonStore, DialogIndexEntry
from .session import SessionManager, ActiveSession
from .gemini import GeminiClient


WELCOME = (
    "Привет! Я бот, который анализирует фото и отвечает на вопросы по ним.\n"
    "Отправьте фото с подписью-вопросом, чтобы начать новый диалог.\n"
    "Важно: 1 фото = 1 диалог. Новое фото — новая сессия."
)

CONTENT_WARNING = (
    "Предупреждение: изображения могут содержать чувствительный контент."
)


class BotHandlers:
    def __init__(
        self,
        store: JsonStore,
        sessions: SessionManager,
        gemini: GeminiClient,
        retention_days: int,
        admins: tuple[str, ...],
    ) -> None:
        self.store = store
        self.sessions = sessions
        self.gemini = gemini
        self.retention_days = retention_days
        self.admins = set(admins)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        u = update.effective_user
        if not u:
            return
        self.store.init_user_if_needed(
            chat_id=u.id,
            username=u.username,
            first_name=u.first_name,
            last_name=u.last_name,
        )
        await update.effective_message.reply_text(WELCOME + "\n" + CONTENT_WARNING)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            "Как пользоваться:\n"
            "- Отправьте фото с подписью-вопросом — начнется новый диалог.\n"
            "- Пишите текстом — продолжение текущего диалога.\n"
            "Команды:\n"
            "/history [N] — показать последние N диалогов (по умолчанию 5).\n"
            "/dialog <id> [full] — показать выжимку или полный диалог.\n"
            "/clear [current|all] — очистка диалога или всей истории.\n"
            "/stats [me|global] — статистика. global — только для админов.\n"
        )
        await update.effective_message.reply_text(text)

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        u = update.effective_user
        if not u:
            return
        args = context.args or []
        scope = args[0].lower() if args else "me"
        if scope == "global":
            if str(u.id) not in self.admins:
                await update.effective_message.reply_text("Недостаточно прав.")
                return
            stats = self.store.global_stats()
            await update.effective_message.reply_text(
                f"Пользователей: {stats['users']}, Диалогов: {stats['dialogs']}, Запросов: {stats['requests']}"
            )
        else:
            stats = self.store.user_stats(u.id)
            last = stats.get("last_active_at")
            last_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "—"
            await update.effective_message.reply_text(
                f"Ваши статистика — Диалогов: {stats['dialogs']}, Запросов: {stats['requests']}, Последняя активность: {last_str}"
            )

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        u = update.effective_user
        if not u:
            return
        # prune old on history
        self.store.prune_old(self.retention_days)
        args = context.args or []
        try:
            limit = int(args[0]) if args else 5
        except ValueError:
            limit = 5
        lst = self.store.list_dialogs(u.id, limit=limit)
        if not lst:
            await update.effective_message.reply_text("История пуста.")
            return
        lines = []
        for e in lst:
            started = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.get("started_at", 0)))
            title = e.get("title") or "(без заголовка)"
            lines.append(f"• {e.get('dialog_id')} — {started}: {title}")
        await update.effective_message.reply_text("\n".join(lines))

    async def cmd_dialog(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        u = update.effective_user
        if not u:
            return
        self.store.prune_old(self.retention_days)
        if not context.args:
            await update.effective_message.reply_text("Укажите id диалога: /dialog <id> [full]")
            return
        dialog_id = context.args[0]
        full = len(context.args) > 1 and context.args[1].lower() == "full"
        data = self.store.get_dialog(u.id, dialog_id)
        if not data:
            await update.effective_message.reply_text("Диалог не найден.")
            return
        if full:
            # Печатаем кратко, чтобы не перегрузить
            msgs = data.get("messages", [])
            text = [f"Диалог {dialog_id}:"]
            for m in msgs[:50]:
                role = m.get("role")
                t = m.get("text", "")
                text.append(f"[{role}] {t[:800]}")
            if len(msgs) > 50:
                text.append("…(обрезано)" )
            await update.effective_message.reply_text("\n".join(text))
        else:
            title = data.get("summary") or "(выжимка не сформирована)"
            await update.effective_message.reply_text(f"{dialog_id}: {title}")

    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        u = update.effective_user
        if not u:
            return
        args = context.args or []
        mode = args[0].lower() if args else "current"
        if mode not in ("current", "all"):
            await update.effective_message.reply_text("Использование: /clear [current|all]")
            return
        if mode == "current":
            s = self.sessions.get(u.id)
            if not s:
                await update.effective_message.reply_text("Нет активного диалога.")
                return
            self.store.delete_dialog(u.id, s.dialog_id)
            self.sessions.clear(u.id)
            await update.effective_message.reply_text("Текущий диалог удален.")
        else:
            cnt = self.store.clear_all_dialogs(u.id)
            self.sessions.clear(u.id)
            await update.effective_message.reply_text(f"Удалено диалогов: {cnt}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        u = update.effective_user
        if not msg or not u:
            return
        # prune old on each message
        self.store.prune_old(self.retention_days)
        self.store.init_user_if_needed(u.id, u.username, u.first_name, u.last_name)

        # Фото
        if msg.photo:
            # Берем самое большое
            photo = msg.photo[-1]
            file = await photo.get_file()
            bio = io.BytesIO()
            await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
            await file.download_to_memory(out=bio)
            image_bytes = bio.getvalue()
            mime = "image/jpeg"
            image_meta = {
                "file_unique_id": photo.file_unique_id,
                "width": photo.width,
                "height": photo.height,
                "size_bytes": len(image_bytes),
                "mime": mime,
            }
            caption = msg.caption or "Опиши изображение, пожалуйста."

            # новый диалог всегда на новое фото
            dialog_id = time.strftime("%Y%m%d-%H%M%S")
            self.store.open_dialog(u.id, dialog_id, model="gemini-1.5-flash", image_meta=image_meta, caption_text=caption)
            self.store.add_dialog_index_entry(
                u.id,
                DialogIndexEntry(
                    dialog_id=dialog_id,
                    started_at=time.time(),
                    closed_at=None,
                    title="",
                    has_image=True,
                    message_count=0,
                    tokens_estimate=0,
                    warning_shown=True,
                ),
            )

            # Инициализация чата и первый ответ внутри одного и того же chat (с учетом system prompt)
            try:
                chat, answer = await self.gemini.start_chat_and_answer_first(
                    image_bytes=image_bytes,
                    mime_type=mime,
                    text=caption,
                )
            except RuntimeError as e:
                code = str(e)
                if code == "gemini_region_blocked":
                    await msg.reply_text(
                        "К сожалению, доступ к модели ограничен по региону. Попробуйте позже или через другой регион."
                    )
                else:
                    await msg.reply_text(
                        "Не удалось получить ответ от модели. Попробуйте повторить запрос позже."
                    )
                return
            session = ActiveSession(
                dialog_id=dialog_id,
                gemini_chat=chat,
                last_activity_at=time.time(),
                last_image_meta=image_meta,
                message_seq=0,
            )
            self.sessions.set(u.id, session)

            # Ответ уже получен внутри чата; просто отправим typing и продолжим сохранение
            await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)

            # Запись сообщений
            session.message_seq += 1
            self.store.append_message(
                u.id,
                dialog_id,
                {
                    "message_id": session.message_seq,
                    "timestamp": time.time(),
                    "role": "user",
                    "type": "image+text",
                    "text": caption,
                    "tokens_estimate": 0,
                    "latency_ms": 0,
                    "error": None,
                },
            )
            session.message_seq += 1
            self.store.append_message(
                u.id,
                dialog_id,
                {
                    "message_id": session.message_seq,
                    "timestamp": time.time(),
                    "role": "assistant",
                    "type": "text",
                    "text": answer,
                    "tokens_estimate": 0,
                    "latency_ms": 0,
                    "error": None,
                },
            )
            await msg.reply_text(answer)
            return

        # Текст
        if msg.text:
            session = self.sessions.get(u.id)
            if not session:
                await msg.reply_text("Отправьте фото с подписью, чтобы начать новый диалог.")
                return
            prompt = msg.text
            await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
            # Используем gemini chat для продолжения контекста (с ретраями)
            try:
                text = await self.gemini.send_chat_message(session.gemini_chat, prompt)
            except RuntimeError as e:
                code = str(e)
                if code == "gemini_region_blocked":
                    await msg.reply_text(
                        "К сожалению, доступ к модели ограничен по региону. Попробуйте позже или через другой регион."
                    )
                else:
                    await msg.reply_text(
                        "Не удалось получить ответ от модели. Попробуйте повторить запрос позже."
                    )
                return

            session.message_seq += 1
            self.store.append_message(
                u.id,
                session.dialog_id,
                {
                    "message_id": session.message_seq,
                    "timestamp": time.time(),
                    "role": "user",
                    "type": "text",
                    "text": prompt,
                    "tokens_estimate": 0,
                    "latency_ms": 0,
                    "error": None,
                },
            )
            session.message_seq += 1
            self.store.append_message(
                u.id,
                session.dialog_id,
                {
                    "message_id": session.message_seq,
                    "timestamp": time.time(),
                    "role": "assistant",
                    "type": "text",
                    "text": text,
                    "tokens_estimate": 0,
                    "latency_ms": 0,
                    "error": None,
                },
            )
            await msg.reply_text(text)


