import json
import logging
import os
from pathlib import Path

from app_paths import config_directory, migrate_legacy_config

logger = logging.getLogger("Config")

CONFIG_FILE = config_directory() / "config.json"
DEFAULT_SERVER_URL = "https://taskstack-o9vw.onrender.com"
LEGACY_LOCAL_SERVER_URLS = {"http://127.0.0.1:8000", "http://localhost:8000"}

DEFAULT_CONFIG = {
    "organization_name": "MTUCI",
    "application_name": "TaskManagerLab",
    "default_opacity": 0.7,
    "default_window_width": 600,
    "default_window_height": 580,
    "default_language": "ru",
    "ai_url": "http://localhost:11434/api/generate",
    "ai_model": "llama3",
    "ai_api_key": "",
    "server_url": DEFAULT_SERVER_URL,
    "categories": [
        "💻 Разработка",
        "📚 Учёба",
        "🏠 Личное",
        "📌 Прочее"
    ]
}

TRANSLATIONS = {
    "ru": {
        "title": "Менеджер задач",
        "new_task_placeholder": "Название новой задачи...",
        "add_btn": "Добавить",
        "ai_btn": "🤖 ИИ-задача",
        "search_placeholder": "🔍 Поиск по задачам...",
        "all_categories": "Все категории",
        "filter_all": "Все",
        "filter_active": "Активные",
        "filter_completed": "Завершённые",
        "delete_btn": "🗑 Удалить",
        "clear_btn": "🧹 Очистить всё",
        "settings_title": "Настройки",
        "opacity_label": "Степень полупрозрачности:",
        "lang_label": "Язык интерфейса / Language:",
        "api_key_label": "API ключ ИИ (необязательно):",
        "api_key_placeholder": "sk-...",
        "reset_btn": "Сбросить по умолчанию",
        "save_btn": "Готово",
        "priorities": ["⚡ Средний", "🔥 Высокий", "☕ Низкий"],
        "categories": [
            "💻 Разработка",
            "📚 Учёба",
            "🏠 Личное",
            "📌 Прочее"
        ]
    },
    "en": {
        "title": "Task Manager",
        "new_task_placeholder": "New task title...",
        "add_btn": "Add",
        "ai_btn": "🤖 AI Task",
        "search_placeholder": "🔍 Search tasks...",
        "all_categories": "All Categories",
        "filter_all": "All",
        "filter_active": "Active",
        "filter_completed": "Completed",
        "delete_btn": "🗑 Delete",
        "clear_btn": "🧹 Clear All",
        "settings_title": "Settings",
        "opacity_label": "Window Opacity:",
        "lang_label": "Language / Язык интерфейса:",
        "api_key_label": "AI API Key (optional):",
        "api_key_placeholder": "sk-...",
        "reset_btn": "Reset to Default",
        "save_btn": "Done",
        "priorities": ["⚡ Medium", "🔥 High", "☕ Low"],
        "categories": [
            "💻 Development",
            "📚 Study",
            "🏠 Personal",
            "📌 Other"
        ]
    }
}


def is_legacy_taskstack_config(config_file):
    try:
        with Path(config_file).open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return False

    return (
        isinstance(data, dict)
        and data.get("organization_name") == DEFAULT_CONFIG["organization_name"]
        and data.get("application_name") == DEFAULT_CONFIG["application_name"]
        and "server_url" in data
    )


def load_config(config_file=CONFIG_FILE, legacy_config_file=None):
    config_file = Path(config_file)
    if legacy_config_file is None:
        legacy_config_file = Path.cwd() / "config.json"

    if not config_file.exists():
        try:
            migrated = migrate_legacy_config(
                legacy_config_file, config_file, is_legacy_taskstack_config
            )
        except OSError as error:
            logger.error("Не удалось перенести старую конфигурацию: %s", error)
            migrated = False

        if migrated:
            logger.info("Перенесена старая конфигурация в пользовательскую папку приложения.")

    if config_file.exists():
        try:
            with config_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
                logger.info("Конфигурация успешно загружена из %s", config_file)
                return {**DEFAULT_CONFIG, **data}
        except (OSError, json.JSONDecodeError, TypeError) as error:
            logger.error("Ошибка чтения конфигурации %s: %s", config_file, error)
    else:
        try:
            with config_file.open("w", encoding="utf-8") as file:
                json.dump(DEFAULT_CONFIG, file, indent=4, ensure_ascii=False)
                logger.info("Создан новый файл config.json со значениями по умолчанию.")
        except OSError as error:
            logger.error("Не удалось создать конфигурацию %s: %s", config_file, error)

    return DEFAULT_CONFIG


config_data = load_config()

ORGANIZATION_NAME = config_data["organization_name"]
APPLICATION_NAME = config_data["application_name"]
DEFAULT_OPACITY = config_data["default_opacity"]
DEFAULT_WINDOW_WIDTH = config_data["default_window_width"]
DEFAULT_WINDOW_HEIGHT = config_data["default_window_height"]
AI_URL = config_data["ai_url"]
AI_MODEL = config_data["ai_model"]
AI_API_KEY = config_data["ai_api_key"]


def resolve_server_url(config, environ):
    server_url = environ.get("TASKSTACK_SERVER_URL", "").strip()
    if not server_url:
        server_url = config.get("server_url", DEFAULT_SERVER_URL)
        if server_url in LEGACY_LOCAL_SERVER_URLS:
            server_url = DEFAULT_SERVER_URL
    return server_url.rstrip("/")


SERVER_URL = resolve_server_url(config_data, os.environ)
CATEGORIES = config_data["categories"]