import os
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

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
    gemini = GeminiClient(cfg.gemini_api_key)
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

    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handlers.handle_message))

    return app


