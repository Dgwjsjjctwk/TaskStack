import json
import os
import logging

logger = logging.getLogger("Config")

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "organization_name": "MTUCI",
    "application_name": "TaskManagerLab",
    "default_opacity": 0.7,
    "default_window_width": 550,
    "default_window_height": 550,
    "categories": [
        "💻 Разработка",
        "📚 Учёба",
        "🏠 Личное",
        "📌 Прочее"
    ]
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
CATEGORIES = config_data["categories"]

DARK_GRADIENT_STYLE = """
/* Главное окно и диалоги */
QMainWindow, QDialog {
    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, 
                                stop: 0 #2b303c, 
                                stop: 1 #0a1128);
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 14px;
    color: #e2e8f0;
    border-radius: 12px;
}

/* Поля ввода, выпадающие списки и выбор дат */
QLineEdit, QComboBox, QDateEdit {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 6px 10px;
    color: #ffffff;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 2px solid #388bfd;
}
QComboBox::drop-down, QDateEdit::drop-down {
    border: 0px;
}
QComboBox QAbstractItemView, QDateEdit QAbstractItemView {
    background-color: #161b22;
    color: #ffffff;
    selection-background-color: #1f6feb;
    border: 1px solid #30363d;
}

/* Стандартные кнопки */
QPushButton {
    background-color: #21262d;
    border: 1px solid #363b42;
    border-radius: 8px;
    padding: 6px 14px;
    font-weight: 500;
    color: #c9d1d9;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #8b949e;
}
QPushButton:pressed {
    background-color: #161b22;
}

/* Акцентная кнопка «Добавить» */
QPushButton#AddButton {
    background-color: #238636;
    color: white;
    border: none;
}
QPushButton#AddButton:hover {
    background-color: #2ea043;
}

/* Кнопки фильтров */
QPushButton#FilterBtn {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    color: #8b949e;
}
QPushButton#FilterBtn:hover {
    background-color: #21262d;
    color: #e2e8f0;
}
QPushButton#FilterBtn[active="true"] {
    background-color: #1f6feb;
    border-color: #388bfd;
    color: #ffffff;
    font-weight: 600;
}

/* Кнопки управления окном */
QPushButton#IconButton, QPushButton#WindowButton {
    background-color: #21262d;
    border: 1px solid #363b42;
    border-radius: 16px;
    padding: 0px;
    margin: 0px;
    font-size: 14px;
    color: #c9d1d9;
}
QPushButton#IconButton:hover, QPushButton#WindowButton:hover {
    background-color: #30363d;
}

QPushButton#CloseButton {
    background-color: #21262d;
    border: 1px solid #363b42;
    border-radius: 16px;
    padding: 0px;
    margin: 0px;
    font-size: 13px;
    font-weight: bold;
    color: #c9d1d9;
}
QPushButton#CloseButton:hover {
    background-color: #da3633;
    color: white;
    border-color: #da3633;
}

/* Кружки статуса задачи */
QPushButton#GreenBtn {
    background-color: #198754;
    border: none;
    border-radius: 12px;
}
QPushButton#GreenBtn:hover {
    background-color: #157347;
}

QPushButton#RedBtn {
    background-color: #dc3545;
    border: none;
    border-radius: 12px;
}
QPushButton#RedBtn:hover {
    background-color: #bb2d3b;
}

/* Нижние компактные кнопки */
QPushButton#ActionBtn {
    background-color: #21262d;
    border: 1px solid #363b42;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 400;
    color: #c9d1d9;
}
QPushButton#ActionBtn:hover {
    background-color: #30363d;
    border-color: #8b949e;
    color: #ffffff;
}

/* Список задач */
QListWidget {
    background-color: #111625;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 4px;
}
QListWidget::item {
    background-color: #1b2234;
    border-bottom: 1px solid #28324a;
    border-radius: 6px;
    margin-bottom: 4px;
    padding: 4px;
    color: #e2e8f0;
}
QListWidget::item:selected {
    background-color: #1f6feb;
    color: #ffffff;
}

/* Прогресс-бар */
QProgressBar {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
    font-size: 11px;
}
QProgressBar::chunk {
    background-color: #238636;
    border-radius: 3px;
}

/* Слайдер */
QSlider::groove:horizontal {
    border: 1px solid #30363d;
    height: 6px;
    background: #161b22;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #58a6ff;
    border: none;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

QLabel {
    color: #e2e8f0;
    font-weight: 500;
}
"""