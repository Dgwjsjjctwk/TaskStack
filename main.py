import sys
import ctypes
import logging
from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon
from PyQt6.QtCore import Qt
from main_window import MainWindow, AuthDialog

def setup_logging():
    """Настройка логирования в консоль и в файл app.log"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("app.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

def create_app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    painter.setBrush(QColor("#1f6feb"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Segoe UI", 30, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "✓")
    painter.end()
    
    return QIcon(pixmap)

if sys.platform == 'win32':
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('MTUCI.TaskManager.App.1.1')

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

/* Поля ввода и выпадающий список */
QLineEdit, QComboBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 8px 12px;
    color: #ffffff;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QComboBox:focus {
    border: 2px solid #388bfd;
}
QComboBox::drop-down {
    border: 0px;
}
QComboBox QAbstractItemView {
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

def main():
    setup_logging()
    logger = logging.getLogger("Main")
    logger.info("Запуск приложения из main.py...")

    app = QApplication(sys.argv)
    app_icon = create_app_icon()
    app.setWindowIcon(app_icon)
    app.setStyleSheet(DARK_GRADIENT_STYLE)
    
    # Открываем диалоговое окно авторизации / регистрации
    auth_dialog = AuthDialog()
    auth_dialog.setWindowIcon(app_icon)
    
    if auth_dialog.exec() == QDialog.DialogCode.Accepted:
        user_id = auth_dialog.user_id
        username = auth_dialog.username
        
        # Передаем авторизованного пользователя в главное окно
        window = MainWindow(user_id=user_id, username=username)
        window.setWindowIcon(app_icon)
        window.show()
        
        logger.info(f"Главное окно успешно отображено для пользователя '{username}' (ID: {user_id}).")
        sys.exit(app.exec())
    else:
        logger.info("Авторизация отменена пользователем.")
        sys.exit(0)

if __name__ == "__main__":
    main()