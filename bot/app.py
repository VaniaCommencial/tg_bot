import os
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.error import TelegramError

from .config import load_config
from .storage import JsonStore
from .session import SessionManager
from .gemini import GeminiClient
from .handlers import BotHandlers


async def create_application():
    cfg = load_config()

    # Ensure folders exist
    os.makedirs(cfg.data_dir, exist_ok=True)
    os.makedirs(cfg.logs_dir, exist_ok=True)

    store = JsonStore(cfg.data_dir)
    sessions = SessionManager(cfg.idle_timeout_minutes)
    # Load system prompt if present
    system_prompt = ""
    if os.path.exists(cfg.system_prompt_path):
        try:
            with open(cfg.system_prompt_path, "r", encoding="utf-8") as f:
                system_prompt = f.read().strip()
        except Exception:
            system_prompt = ""

    gemini = GeminiClient(cfg.gemini_api_key, system_prompt=system_prompt)
    handlers = BotHandlers(store, sessions, gemini, cfg.retention_days, cfg.admins)

    app = (
        ApplicationBuilder()
        .token(cfg.telegram_token)
        .build()
    )

    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("history", handlers.cmd_history))
    app.add_handler(CommandHandler("dialog", handlers.cmd_dialog))
    app.add_handler(CommandHandler("clear", handlers.cmd_clear))

    app.add_handler(MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), handlers.handle_message))

    async def on_error(update, context):
        try:
            raise context.error
        except Exception:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "Произошла ошибка. Попробуйте повторить запрос позже."
                )

    app.add_error_handler(on_error)

    return app


