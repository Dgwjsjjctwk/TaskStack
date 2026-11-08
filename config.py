import json
import os
import logging

logger = logging.getLogger("Config")

CONFIG_FILE = "config.json"
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

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("Конфигурация успешно загружена из config.json")
                return {**DEFAULT_CONFIG, **data}
        except Exception as e:
            logger.error(f"Ошибка чтения config.json: {e}. Используются настройки по умолчанию.")
    else:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
                logger.info("Создан новый файл config.json со значениями по умолчанию.")
        except Exception as e:
            logger.error(f"Не удалось создать config.json: {e}")
            
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
SERVER_URL = os.environ.get("TASKSTACK_SERVER_URL", "").strip()
if not SERVER_URL:
    SERVER_URL = config_data["server_url"]
    if SERVER_URL in LEGACY_LOCAL_SERVER_URLS:
        SERVER_URL = DEFAULT_SERVER_URL
SERVER_URL = SERVER_URL.rstrip("/")
CATEGORIES = config_data["categories"]