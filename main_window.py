import logging
import urllib.error
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton, 
    QListWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QListWidgetItem,
    QDialog, QSlider, QComboBox, QProgressBar, QDateTimeEdit, QSystemTrayIcon, QMenu, QTextEdit, QCheckBox,
    QGraphicsOpacityEffect, QSizePolicy
)
from PyQt6.QtCore import Qt, QSettings, QPoint, QTimer, QDateTime, QDate, QPropertyAnimation, QEasingCurve, QSize
from PyQt6.QtGui import QColor, QIcon
from config import (
    ORGANIZATION_NAME, APPLICATION_NAME, DEFAULT_OPACITY, 
    DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT, TRANSLATIONS, 
    AI_URL, AI_MODEL, AI_API_KEY
)
from desktop_net import (
    ApiError, ServerProbe, client, clear_completed, describe_error, request_ai_task
)
from qt_async import run_async

logger = logging.getLogger("MainWindow")

# How often the network indicator asks the server whether it is alive.
HEARTBEAT_INTERVAL_MS = 30_000


class AuthDialog(QDialog):
    """Окно авторизации и регистрации пользователя"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.resize(320, 260)
        self.user_id = None
        self.username = None
        self.access_token = None
        self.is_register_mode = False

        layout = QVBoxLayout(self)

        self.title_label = QLabel("🔑 Вход в систему")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.title_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Имя пользователя...")
        layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Пароль...")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_input)

        self.submit_btn = QPushButton("Войти")
        self.submit_btn.setObjectName("AddButton")
        self.submit_btn.clicked.connect(self.handle_submit)
        layout.addWidget(self.submit_btn)

        self.toggle_btn = QPushButton("Нет аккаунта? Зарегистрироваться")
        self.toggle_btn.setStyleSheet("background: transparent; color: #388bfd; text-decoration: underline;")
        self.toggle_btn.clicked.connect(self.toggle_mode)
        layout.addWidget(self.toggle_btn)

    def toggle_mode(self):
        self.is_register_mode = not self.is_register_mode
        if self.is_register_mode:
            self.title_label.setText("📝 Регистрация")
            self.submit_btn.setText("Зарегистрироваться")
            self.toggle_btn.setText("Уже есть аккаунт? Войти")
        else:
            self.title_label.setText("🔑 Вход в систему")
            self.submit_btn.setText("Войти")
            self.toggle_btn.setText("Нет аккаунта? Зарегистрироваться")

    def handle_submit(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Ошибка", "Заполните все поля!")
            return

        register = self.is_register_mode

        # The server may be asleep and need up to a minute to answer; the call
        # runs on a worker thread, so the window stays alive and says so.
        self.submit_btn.setEnabled(False)
        self.submit_btn.setText("Подключение к серверу… (до минуты, если он спал)")

        def request():
            if register:
                return client.register(username, password)
            return client.login(username, password)

        run_async(
            request,
            lambda data: self._on_auth_done(register, data),
            self._on_auth_failed,
        )

    def _restore_submit_button(self):
        self.submit_btn.setEnabled(True)
        # The mode may have just changed (successful registration).
        self.submit_btn.setText("Зарегистрироваться" if self.is_register_mode else "Войти")

    def _on_auth_done(self, register, data):
        self._restore_submit_button()
        if register:
            QMessageBox.information(self, "Успех", "Регистрация успешна! Теперь выполните вход.")
            self.toggle_mode()
            self._restore_submit_button()
            return
        self.user_id = data.get("id")
        self.username = data.get("username")
        self.access_token = data.get("access_token")
        self.accept()

    def _on_auth_failed(self, error):
        self._restore_submit_button()
        if isinstance(error, ApiError):
            QMessageBox.critical(self, "Ошибка", error.detail or "Ошибка авторизации")
        else:
            QMessageBox.critical(self, "Ошибка сети", f"Не удалось связаться с сервером: {describe_error(error)}")


class GroupCreateDialog(QDialog):
    """Диалог создания новой рабочей группы"""
    def __init__(self, current_user_id, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.resize(300, 300)
        self.current_user_id = current_user_id
        self.group_created = False

        layout = QVBoxLayout(self)

        title_label = QLabel("🏢 Создать группу")
        title_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title_label)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Название группы (напр. Разработка)...")
        layout.addWidget(self.name_input)

        label_members = QLabel("Выберите участников:")
        layout.addWidget(label_members)

        self.members_list = QListWidget()
        layout.addWidget(self.members_list)
        self.load_users()

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("Создать")
        self.save_btn.setObjectName("AddButton")
        self.save_btn.clicked.connect(self.save_group)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

    def load_users(self):
        run_async(client.list_users, self._fill_users, self._users_failed)

    def _fill_users(self, users):
        for user in users:
            item = QListWidgetItem(user["username"])
            item.setData(Qt.ItemDataRole.UserRole, user["id"])
            item.setCheckState(Qt.CheckState.Unchecked)
            self.members_list.addItem(item)

    def _users_failed(self, error):
        logger.error(f"Не удалось загрузить пользователей для группы: {error}")
        self.members_list.addItem(f"⚠ Не удалось загрузить: {describe_error(error)}")

    def save_group(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название группы!")
            return

        member_ids = []
        for i in range(self.members_list.count()):
            item = self.members_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                member_ids.append(item.data(Qt.ItemDataRole.UserRole))

        self.save_btn.setEnabled(False)
        run_async(
            lambda: client.create_group(name, member_ids),
            self._group_saved,
            self._group_failed,
        )

    def _group_saved(self, _result):
        self.group_created = True
        self.accept()

    def _group_failed(self, error):
        self.save_btn.setEnabled(True)
        if isinstance(error, ApiError):
            QMessageBox.critical(self, "Ошибка", error.detail or "Ошибка создания группы")
        else:
            QMessageBox.critical(self, "Ошибка сети", f"Не удалось создать группу: {describe_error(error)}")


class ShareDialog(QDialog):
    """Окно выбора пользователей и групп для совместного доступа"""
    def __init__(self, current_user_id, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.resize(360, 400)
        self.current_user_id = current_user_id
        self.selected_user_ids = []
        self.selected_group_ids = []

        layout = QVBoxLayout(self)

        title_label = QLabel("👥 Совместный доступ")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        layout.addWidget(QLabel("Пользователи:"))
        self.search_users_input = QLineEdit()
        self.search_users_input.setPlaceholderText("🔍 Найти пользователя...")
        self.search_users_input.textChanged.connect(self.filter_users)
        layout.addWidget(self.search_users_input)

        self.users_list = QListWidget()
        layout.addWidget(self.users_list)

        groups_header_layout = QHBoxLayout()
        groups_header_layout.addWidget(QLabel("Группы:"))
        self.create_group_btn = QPushButton("+ Создать группу")
        self.create_group_btn.clicked.connect(self.open_create_group)
        groups_header_layout.addWidget(self.create_group_btn)
        layout.addLayout(groups_header_layout)

        self.groups_list = QListWidget()
        layout.addWidget(self.groups_list)

        self.load_data()

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QPushButton("Готово")
        confirm_btn.setObjectName("AddButton")
        confirm_btn.clicked.connect(self.confirm_selection)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

    def load_data(self):
        self.users_list.clear()
        self.groups_list.clear()
        self.users_list.addItem("Загрузка…")
        self._load_generation = getattr(self, "_load_generation", 0) + 1
        generation = self._load_generation

        def fetch():
            return client.list_users(), client.list_groups()

        run_async(
            fetch,
            lambda data: self._fill_data(generation, *data),
            lambda error: self._data_failed(generation, error),
        )

    def _fill_data(self, generation, users, groups):
        if generation != self._load_generation:
            return  # a newer load (after creating a group) is on its way
        self.users_list.clear()
        for user in users:
            item = QListWidgetItem(f"👤 {user['username']}")
            item.setData(Qt.ItemDataRole.UserRole, user["id"])
            item.setCheckState(Qt.CheckState.Unchecked)
            self.users_list.addItem(item)
        for group in groups:
            item = QListWidgetItem(f"🏢 {group['name']} (участников: {len(group['member_ids'])})")
            item.setData(Qt.ItemDataRole.UserRole, group["id"])
            item.setCheckState(Qt.CheckState.Unchecked)
            self.groups_list.addItem(item)

    def _data_failed(self, generation, error):
        if generation != self._load_generation:
            return
        logger.error(f"Не удалось загрузить данные для шеринга: {error}")
        self.users_list.clear()
        self.users_list.addItem(f"⚠ Не удалось загрузить: {describe_error(error)}")

    def filter_users(self, text):
        query = text.strip().lower()
        for i in range(self.users_list.count()):
            item = self.users_list.item(i)
            if query in item.text().lower() or item.checkState() == Qt.CheckState.Checked:
                item.setHidden(False)
            else:
                item.setHidden(True)

    def open_create_group(self):
        dialog = GroupCreateDialog(self.current_user_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_data()

    def confirm_selection(self):
        self.selected_user_ids = []
        for i in range(self.users_list.count()):
            item = self.users_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self.selected_user_ids.append(item.data(Qt.ItemDataRole.UserRole))

        self.selected_group_ids = []
        for i in range(self.groups_list.count()):
            item = self.groups_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self.selected_group_ids.append(item.data(Qt.ItemDataRole.UserRole))

        self.accept()


class TaskItemWidget(QWidget):
    """Идеально выровненный виджет задачи с видимыми кнопками и без обрезки текста"""
    def __init__(self, text, completed=False, priority="⚡ Средний", category="💻 Разработка", deadline="", author=""):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self.setFixedHeight(44)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        
        self.priority = priority
        self.category = category
        self.deadline = deadline
        
        # Настройка цветов приоритетов
        p_color = "#8b949e"
        if "Высокий" in priority or "High" in priority:
            p_color = "#f87171"
        elif "Средний" in priority or "Medium" in priority:
            p_color = "#fbbf24"
        elif "Низкий" in priority or "Low" in priority:
            p_color = "#34d399"

        self.priority_label = QLabel(priority)
        self.priority_label.setStyleSheet(f"color: {p_color}; font-size: 12px; font-weight: bold; background: transparent;")
        self.priority_label.setFixedWidth(75)
        self.priority_label.setToolTip(priority)
        
        cat_text = f"[{category}]"
        if author:
            cat_text = f"👥 [{author}] {cat_text}"

        self.cat_label = QLabel(cat_text)
        self.cat_label.setStyleSheet("color: #8b949e; font-size: 11px; background: transparent;")
        self.cat_label.setFixedWidth(112)
        self.cat_label.setToolTip(cat_text)

        # Текст задачи (занимает всё оставшееся пространство)
        self.task_text = text
        self.label = QLabel(text)
        self.label.setMinimumWidth(0)
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.label.setToolTip(text)
        
        self.deadline_label = QLabel()
        self.deadline_label.setFixedWidth(150)
        self.deadline_label.setToolTip(deadline)
        
        # Компактные кнопки статуса справа (теперь гарантированно видимые)
        self.green_btn = QPushButton("✓")
        self.green_btn.setObjectName("GreenBtn")
        self.green_btn.setFixedSize(30, 30)
        self.green_btn.setStyleSheet(
            "QPushButton { background-color: #238636; color: white; border: 1px solid #2ea043; "
            "border-radius: 6px; font-size: 17px; font-weight: bold; }"
            "QPushButton:hover { background-color: #2ea043; }"
            "QPushButton:pressed { background-color: #196c2e; }"
        )
        self.green_btn.setToolTip("Выполнить")
        self.green_btn.clicked.connect(self.set_completed)
        
        self.red_btn = QPushButton("✕")
        self.red_btn.setObjectName("RedBtn")
        self.red_btn.setFixedSize(30, 30)
        self.red_btn.setStyleSheet(
            "QPushButton { background-color: #da3633; color: white; border: 1px solid #f85149; "
            "border-radius: 6px; font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #f85149; }"
            "QPushButton:pressed { background-color: #b62324; }"
        )
        self.red_btn.setToolTip("Вернуть в активные")
        self.red_btn.clicked.connect(self.set_uncompleted)
        
        self.update_text_style(completed)
        self.update_deadline_style(completed)

        # Keep the status action visible before task text and metadata.
        layout.addWidget(self.green_btn)
        layout.addWidget(self.red_btn)
        layout.addWidget(self.priority_label)
        layout.addWidget(self.cat_label)
        layout.addWidget(self.label, 1)
        if deadline:
            layout.addWidget(self.deadline_label)
        
    def update_text_style(self, completed):
        self.completed = completed
        font = self.label.font()
        font.setStrikeOut(completed)
        self.label.setFont(font)
        self.green_btn.setVisible(not completed)
        self.red_btn.setVisible(completed)
        if completed:
            self.label.setStyleSheet("color: #9ca3af; background: transparent;")
        else:
            self.label.setStyleSheet("color: #f3f4f6; background: transparent;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.update_elided_text)

    def update_elided_text(self):
        available_width = max(0, self.label.contentsRect().width())
        visible_text = self.label.fontMetrics().elidedText(
            self.task_text, Qt.TextElideMode.ElideRight, available_width
        )
        if self.label.text() != visible_text:
            self.label.setText(visible_text)

    def update_deadline_style(self, completed):
        if not self.deadline:
            return
        self.deadline_label.setText(f"📅 {self.deadline}")
        if not completed:
            due_datetime = QDateTime.fromString(self.deadline, "yyyy-MM-dd HH:mm")
            if not due_datetime.isValid():
                due_date = QDate.fromString(self.deadline, "yyyy-MM-dd")
                if due_date.isValid():
                    due_datetime = due_date.startOfDay()

            if due_datetime.isValid() and due_datetime < QDateTime.currentDateTime():
                self.deadline_label.setStyleSheet("color: #da3633; font-size: 11px; font-weight: bold; background: transparent;")
            else:
                self.deadline_label.setStyleSheet("color: #8b949e; font-size: 11px; background: transparent;")
        else:
            self.deadline_label.setStyleSheet("color: #6e7681; font-size: 11px; background: transparent;")

    def get_text(self):
        return self.task_text
        
    def get_priority(self):
        return self.priority

    def get_category(self):
        return self.category

    def get_deadline(self):
        return self.deadline

    def is_completed(self):
        return self.completed

    def update_server_status(self, status):
        window = self.window()
        if hasattr(window, "update_task_status_on_server") and hasattr(self, "task_id") and self.task_id is not None:
            window.update_task_status_on_server(self.task_id, status)

    def set_completed(self):
        self.update_text_style(True)
        self.update_deadline_style(True)
        self.update_server_status(1)
        logger.info(f"Задача отмечена как выполненная: '{self.get_text()}'")
        window = self.window()
        if hasattr(window, "update_stats"):
            window.update_stats()
            window.apply_filters()
        
    def set_uncompleted(self):
        self.update_text_style(False)
        self.update_deadline_style(False)
        self.update_server_status(0)
        logger.info(f"Задача возвращена в активные: '{self.get_text()}'")
        window = self.window()
        if hasattr(window, "update_stats"):
            window.update_stats()
            window.apply_filters()

class AITaskDialog(QDialog):
    """Диалоговое окно для создания задачи с помощью ИИ"""
    def __init__(self, current_lang, api_key="", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.resize(420, 260)
        self.current_lang = current_lang
        self.api_key = api_key
        
        layout = QVBoxLayout(self)
        
        title_text = "🤖 Создать задачу с помощью ИИ" if current_lang == "ru" else "🤖 Create Task with AI"
        self.title_label = QLabel(title_text)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.title_label)
        
        desc_text = "Опишите задачу своими словами (например: 'Купить молоко завтра в 18:00, категория Личное'):" if current_lang == "ru" else "Describe the task in your own words:"
        self.desc_label = QLabel(desc_text)
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)
        
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Сделать домашку по разработке в пятницу в 20:00...")
        layout.addWidget(self.input_text)
        
        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Отмена" if current_lang == "ru" else "Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.generate_btn = QPushButton("Сгенерировать" if current_lang == "ru" else "Generate")
        self.generate_btn.setObjectName("AddButton")
        self.generate_btn.clicked.connect(self.process_with_ai)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.generate_btn)
        layout.addLayout(btn_layout)
        
        self.task_data = None
        self._closed = False

    def process_with_ai(self):
        prompt_text = self.input_text.toPlainText().strip()
        if not prompt_text:
            QMessageBox.warning(self, "Ошибка", "Введите текст задачи!")
            return

        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Обработка..." if self.current_lang == "ru" else "Processing...")

        current_datetime = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm")
        
        system_prompt = f"""
Ты — умный помощник для таск-менеджера. Текущая дата и время: {current_datetime}.
Проанализируй текст пользователя и верни СТРОГО валидный JSON (без лишнего текста, без markdown-оберток вроде ```json) со следующими полями:
- "title": строка, название задачи на русском или английском.
- "category": одна из категорий: "💻 Разработка", "📚 Учёба", "🏠 Личное", "📌 Прочее" (или английские эквиваленты если текст на английском: "💻 Development", "📚 Study", "🏠 Personal", "📌 Other").
- "priority": один из приоритетов: "⚡ Средний", "🔥 Высокий", "☕ Низкий" (или "⚡ Medium", "🔥 High", "☕ Low").
- "deadline": дата и время в формате "yyyy-MM-dd HH:mm". Если время не указано, ставь конец текущего дня (23:59).
"""

        full_prompt = f"{system_prompt}\n\nТекст пользователя: {prompt_text}"
        run_async(
            lambda: request_ai_task(AI_URL, AI_MODEL, full_prompt, self.api_key),
            self._ai_done,
            self._ai_failed,
        )

    def done(self, result):
        self._closed = True  # a late answer from the AI must not pop up
        super().done(result)

    def _restore_generate_button(self):
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("Сгенерировать" if self.current_lang == "ru" else "Generate")

    def _ai_done(self, data):
        if self._closed:
            return
        self.task_data = data
        self.accept()

    def _ai_failed(self, error):
        if self._closed:
            return
        self._restore_generate_button()
        if isinstance(error, urllib.error.URLError):
            QMessageBox.critical(self, "Ошибка ИИ", f"Не удалось подключиться к ИИ серверу.\nУбедитесь, что ИИ запущен по адресу {AI_URL}.\nОшибка: {error}")
        else:
            QMessageBox.critical(self, "Ошибка", f"Не удалось разобрать ответ ИИ: {error}")

    def get_task_data(self):
        return self.task_data


class SettingsDialog(QDialog):
    def __init__(self, current_opacity, current_lang, api_key="", default_opacity=DEFAULT_OPACITY, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.resize(340, 280)
        
        self.default_value = int(default_opacity * 100)
        self.current_lang = current_lang
        
        layout = QVBoxLayout(self)
        
        self.title_label = QLabel("⚙️ Настройки")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.title_label)
        
        self.opacity_text_label = QLabel(f"Степень полупрозрачности: {int(current_opacity * 100)}%")
        layout.addWidget(self.opacity_text_label)
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(20, 100)
        self.slider.setValue(int(current_opacity * 100))
        self.slider.valueChanged.connect(self.slider_changed)
        layout.addWidget(self.slider)
        
        self.lang_label = QLabel("Язык / Language:")
        layout.addWidget(self.lang_label)
        
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Русский (RU)", "ru")
        self.lang_combo.addItem("English (EN)", "en")
        index = self.lang_combo.findData(current_lang)
        if index >= 0:
            self.lang_combo.setCurrentIndex(index)
        self.lang_combo.currentIndexChanged.connect(self.update_texts)
        layout.addWidget(self.lang_combo)
        
        self.api_key_label = QLabel("API ключ ИИ (необязательно):")
        layout.addWidget(self.api_key_label)
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setText(api_key)
        layout.addWidget(self.api_key_input)
        
        self.reset_btn = QPushButton("Сбросить по умолчанию")
        self.reset_btn.clicked.connect(self.reset_to_default)
        layout.addWidget(self.reset_btn)
        
        self.save_btn = QPushButton("Готово")
        self.save_btn.clicked.connect(self.accept)
        layout.addWidget(self.save_btn)
        
        self.update_texts()

    def slider_changed(self, value):
        lang = self.lang_combo.currentData()
        prefix = "Степень полупрозрачности: " if lang == "ru" else "Window Opacity: "
        self.opacity_text_label.setText(f"{prefix}{value}%")
        
    def reset_to_default(self):
        self.slider.setValue(self.default_value)
        self.api_key_input.clear()
        
    def get_opacity(self):
        return self.slider.value() / 100.0

    def get_language(self):
        return self.lang_combo.currentData()

    def get_api_key(self):
        return self.api_key_input.text().strip()

    def update_texts(self):
        lang = self.lang_combo.currentData()
        t = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])
        self.title_label.setText(f"⚙️ {t['settings_title']}")
        self.opacity_text_label.setText(f"{t['opacity_label']} {self.slider.value()}%")
        self.lang_label.setText(t["lang_label"])
        self.api_key_label.setText(t["api_key_label"])
        self.api_key_input.setPlaceholderText(t["api_key_placeholder"])
        self.reset_btn.setText(t["reset_btn"])
        self.save_btn.setText(t["save_btn"])


class MainWindow(QMainWindow):
    def __init__(self, user_id=1, username="User"):
        super().__init__()
        self.user_id = user_id
        self.username = username
        self.selected_shared_users = []
        self.selected_shared_groups = []

        self.setWindowTitle(f"Менеджер задач — [{self.username}]")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(500, 450)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMouseTracking(True)

        self.settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
        saved_opacity = self.settings.value("custom_opacity", DEFAULT_OPACITY, type=float)
        self.custom_opacity = saved_opacity

        saved_lang = self.settings.value("current_language", "ru", type=str)
        self.current_lang = saved_lang

        saved_api_key = self.settings.value("ai_api_key", AI_API_KEY, type=str)
        self.ai_api_key = saved_api_key

        logger.info(f"Запуск MainWindow для пользователя '{self.username}' (ID: {self.user_id})")

        self.is_transparent = False
        self.is_pinned = False
        self.locked_pos = None
        
        self.current_filter = "all"
        self.elapsed_seconds = 0

        # One shared client for the whole app; it is told who is signed in.
        client.user_id = self.user_id
        client.username = self.username
        self._probe = ServerProbe(client)
        self._probe_running = False
        self._tasks_generation = 0
        self._deleting_ids = set()

        self.init_ui()
        self.init_tray()
        self.connect_signals()
        
        self.load_tasks()
        self.update_stats()
        
        self.retranslate_ui()

        # Таймер сессии (время работы приложения)
        self.session_timer = QTimer(self)
        self.session_timer.timeout.connect(self.update_session_timer)
        self.session_timer.start(1000)

        # Таймер пинга сервера (индикатор сети); первая проверка сразу после запуска
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self.check_server_connection)
        self.heartbeat_timer.start(HEARTBEAT_INTERVAL_MS)
        QTimer.singleShot(1000, self.check_server_connection)

    def init_tray(self):
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray_icon = QSystemTrayIcon(self)
        if not self.tray_available:
            logger.warning("Системный трей недоступен; приложение будет закрываться без сворачивания в трей.")
            return

        self.tray_icon.setIcon(self.windowIcon())
        
        tray_menu = QMenu()
        restore_action = tray_menu.addAction("Открыть / Развернуть")
        restore_action.triggered.connect(self.show_from_tray)
        
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Выход")
        quit_action.triggered.connect(self.force_close)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_clicked)
        self.tray_icon.show()

    def show_from_tray(self):
        self.show()
        self.setWindowState(Qt.WindowState.WindowNoState)
        self.raise_()
        self.activateWindow()
        # The indicator is not refreshed while the window is hidden.
        QTimer.singleShot(0, self.check_server_connection)

    def tray_icon_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_from_tray()

    def force_close(self):
        logger.info("Принудительное закрытие из трея...")
        self.tray_icon.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def check_server_connection(self):
        """Лёгкий пинг сервера для индикатора сети.

        Спрашивает /ping, который не обращается к базе данных, а не /health:
        иначе каждый открытый клиент не давал бы базе и серверу уснуть.
        Пока окно скрыто в трей или свёрнуто, сервер не опрашивается.
        """
        if not self.isVisible() or self.isMinimized():
            return
        if self._probe_running:
            return  # the previous answer has not arrived yet
        self._probe_running = True
        run_async(self._probe, self._show_connection, lambda _error: self._show_connection(False))

    def _show_connection(self, online):
        self._probe_running = False
        if online:
            self.net_status_label.setText("🟢")
            self.net_status_label.setToolTip("Сервер онлайн")
        else:
            self.net_status_label.setText("🔴")
            self.net_status_label.setToolTip("Нет связи с сервером!")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        top_layout = QHBoxLayout()
        self.net_status_label = QLabel("🟢")
        self.net_status_label.setToolTip("Проверка соединения с сервером...")
        
        self.label_new_task = QLabel(f"👤 {self.username}")
        
        self.pin_button = QPushButton("📌")
        self.pin_button.setObjectName("IconButton")
        self.pin_button.setFixedSize(32, 32)

        self.opacity_button = QPushButton("👁️")
        self.opacity_button.setObjectName("IconButton")
        self.opacity_button.setFixedSize(32, 32)

        self.settings_button = QPushButton("⚙️")
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setFixedSize(32, 32)

        self.minimize_button = QPushButton("—")
        self.minimize_button.setObjectName("WindowButton")
        self.minimize_button.setFixedSize(32, 32)

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("CloseButton")
        self.close_button.setFixedSize(32, 32)
        
        top_layout.addWidget(self.net_status_label)
        top_layout.addWidget(self.label_new_task)
        top_layout.addStretch()
        top_layout.addWidget(self.pin_button)
        top_layout.addWidget(self.opacity_button)
        top_layout.addWidget(self.settings_button)
        top_layout.addWidget(self.minimize_button)
        top_layout.addWidget(self.close_button)

        t = TRANSLATIONS[self.current_lang]

        # --- Строка 1: Название задачи + Категория + Кнопка Добавить ---
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText(t["new_task_placeholder"])

        self.category_combo = QComboBox()
        self.category_combo.addItems(t["categories"])
        self.category_combo.setFixedWidth(150)

        self.add_button = QPushButton(t["add_btn"])
        self.add_button.setObjectName("AddButton")
        self.add_button.setFixedWidth(100)

        row1_layout = QHBoxLayout()
        row1_layout.addWidget(self.task_input)
        row1_layout.addWidget(self.category_combo)
        row1_layout.addWidget(self.add_button)

        # --- Строка 2: Дата/время + Приоритет + Шеринг + ИИ ---
        self.datetime_edit = QDateTimeEdit()
        self.datetime_edit.setDateTime(QDateTime.currentDateTime())
        self.datetime_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.datetime_edit.setCalendarPopup(True)

        self.priority_combo = QComboBox()
        self.priority_combo.addItems(t["priorities"])
        self.priority_combo.setFixedWidth(130)

        self.share_button = QPushButton("👥 Поделиться")
        self.share_button.clicked.connect(self.open_share_dialog)

        self.ai_button = QPushButton(t["ai_btn"])
        self.ai_button.setStyleSheet("background-color: #1f6feb; color: white; border: none; font-weight: bold; border-radius: 8px; padding: 6px 12px;")

        row2_layout = QHBoxLayout()
        row2_layout.addWidget(self.datetime_edit)
        row2_layout.addWidget(self.priority_combo)
        row2_layout.addWidget(self.share_button)
        row2_layout.addWidget(self.ai_button)

        # Поиск и фильтр по категориям
        search_filter_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(t["search_placeholder"])

        self.category_filter_combo = QComboBox()
        self.category_filter_combo.addItem(t["all_categories"])
        self.category_filter_combo.addItems(t["categories"])
        self.category_filter_combo.setFixedWidth(160)

        search_filter_layout.addWidget(self.search_input)
        search_filter_layout.addWidget(self.category_filter_combo)

        # Панель статус-фильтров
        status_filter_layout = QHBoxLayout()
        self.btn_all = QPushButton(t["filter_all"])
        self.btn_all.setObjectName("FilterBtn")
        self.btn_all.setProperty("active", "true")
        
        self.btn_active = QPushButton(t["filter_active"])
        self.btn_active.setObjectName("FilterBtn")
        self.btn_active.setProperty("active", "false")
        
        self.btn_completed = QPushButton(t["filter_completed"])
        self.btn_completed.setObjectName("FilterBtn")
        self.btn_completed.setProperty("active", "false")

        status_filter_layout.addWidget(self.btn_all)
        status_filter_layout.addWidget(self.btn_active)
        status_filter_layout.addWidget(self.btn_completed)
        
        self.task_list = QListWidget()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.delete_button = QPushButton(t["delete_btn"])
        self.delete_button.setObjectName("ActionBtn")
        
        self.clear_button = QPushButton(t["clear_btn"])
        self.clear_button.setObjectName("ActionBtn")

        self.counter_label = QLabel("Задач: 0")
        self.timer_label = QLabel("⏱️ 00:00")
        self.timer_label.setStyleSheet("color: #8b949e; font-size: 12px;")

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.counter_label)
        bottom_layout.addWidget(self.timer_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.delete_button)
        bottom_layout.addWidget(self.clear_button)

        main_layout.addLayout(top_layout)
        main_layout.addLayout(row1_layout)
        main_layout.addLayout(row2_layout)
        main_layout.addLayout(search_filter_layout)
        main_layout.addLayout(status_filter_layout)
        main_layout.addWidget(self.task_list)
        main_layout.addWidget(self.progress_bar)
        main_layout.addLayout(bottom_layout)

    def connect_signals(self):
        self.add_button.clicked.connect(self.add_task)
        self.ai_button.clicked.connect(self.open_ai_dialog)
        self.task_input.returnPressed.connect(self.add_task)
        self.search_input.textChanged.connect(self.apply_filters)
        self.category_filter_combo.currentTextChanged.connect(self.apply_filters)
        
        self.btn_all.clicked.connect(lambda: self.set_status_filter("all"))
        self.btn_active.clicked.connect(lambda: self.set_status_filter("active"))
        self.btn_completed.clicked.connect(lambda: self.set_status_filter("completed"))
        
        self.pin_button.clicked.connect(self.toggle_pin)
        self.opacity_button.clicked.connect(self.toggle_opacity)
        self.settings_button.clicked.connect(self.open_settings)
        
        self.minimize_button.clicked.connect(self.showMinimized)
        self.close_button.clicked.connect(self.close)

        self.delete_button.clicked.connect(self.delete_task)
        self.clear_button.clicked.connect(self.clear_tasks)

    def open_share_dialog(self):
        dialog = ShareDialog(self.user_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_shared_users = dialog.selected_user_ids
            self.selected_shared_groups = dialog.selected_group_ids
            
            total_selected = len(self.selected_shared_users) + len(self.selected_shared_groups)
            if total_selected > 0:
                self.share_button.setStyleSheet("background-color: #238636; color: white; border: none; border-radius: 8px;")
                self.share_button.setText(f"👥 Выбрано: {total_selected}")
            else:
                self.share_button.setStyleSheet("")
                self.share_button.setText("👥 Поделиться")

    def open_ai_dialog(self):
        dialog = AITaskDialog(self.current_lang, api_key=self.ai_api_key, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_task_data()
            if data:
                title = data.get("title", "Новая задача")
                category = data.get("category", self.category_combo.currentText())
                priority = data.get("priority", self.priority_combo.currentText())
                deadline = data.get("deadline", "")
                
                self.send_task_to_server(
                    title, priority, category, deadline,
                    self.selected_shared_users, self.selected_shared_groups
                )

    def send_task_to_server(self, title, priority, category, deadline, shared_with_ids=(), shared_with_group_ids=()):
        shared_users = list(shared_with_ids)
        shared_groups = list(shared_with_group_ids)
        run_async(
            lambda: client.add_task(title, priority, category, deadline, shared_users, shared_groups),
            lambda result: self._task_sent(result, title, priority, category, deadline, shared_users, shared_groups),
            lambda error: self._request_failed(error, "Не удалось отправить задачу на сервер"),
        )

    def _task_sent(self, result, title, priority, category, deadline, shared_users, shared_groups):
        author_label = self.username if (shared_users or shared_groups) else ""
        self.add_server_task_item(
            result.get("id"), title, False, priority, category, deadline,
            author_label, owner_id=self.user_id
        )
        self.selected_shared_users = []
        self.selected_shared_groups = []
        self.share_button.setStyleSheet("")
        self.share_button.setText("👥 Поделиться")
        self.update_stats()
        self.apply_filters()

    def _request_failed(self, error, what):
        """One place that tells the person why a request did not work."""
        logger.error(f"{what}: {error}")
        if isinstance(error, ApiError) and error.is_unauthorized:
            QMessageBox.warning(
                self,
                "Сессия истекла" if self.current_lang == "ru" else "Session expired",
                "Войдите заново: закройте приложение и откройте его снова."
                if self.current_lang == "ru"
                else "Please sign in again: close the app and open it again.",
            )
            return
        QMessageBox.critical(self, "Ошибка сети", f"{what}: {describe_error(error)}")

    def update_task_status_on_server(self, task_id, status):
        run_async(
            lambda: client.set_task_status(task_id, bool(status)),
            lambda _result: logger.info(f"Статус задачи ID {task_id} обновлен на сервере: {status}"),
            lambda error: self._status_failed(error, task_id),
        )

    def _status_failed(self, error, task_id):
        logger.error(f"Не удалось обновить статус задачи {task_id} на сервере: {error}")
        # The list on screen no longer matches the server: show what it really holds.
        self.load_tasks(quiet=True)

    def set_status_filter(self, filter_name):
        self.current_filter = filter_name
        logger.debug(f"Установлен статус-фильтр: {filter_name}")
        for btn, name in zip([self.btn_all, self.btn_active, self.btn_completed], ["all", "active", "completed"]):
            active = "true" if name == filter_name else "false"
            btn.setProperty("active", active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.apply_filters()

    def apply_filters(self):
        query = self.search_input.text().strip().lower()
        selected_cat = self.category_filter_combo.currentText()
        t = TRANSLATIONS[self.current_lang]
        all_cat_text = t["all_categories"]

        for i in range(self.task_list.count()):
            item = self.task_list.item(i)
            widget = self.task_list.itemWidget(item)
            if widget:
                text = widget.get_text().lower()
                completed = widget.is_completed()
                cat = widget.get_category()
                
                status_match = True
                if self.current_filter == "active":
                    status_match = not completed
                elif self.current_filter == "completed":
                    status_match = completed
                
                cat_match = (selected_cat == all_cat_text) or (cat == selected_cat)
                text_match = query in text
                
                if status_match and cat_match and text_match:
                    item.setHidden(False)
                else:
                    item.setHidden(True)

    def update_stats(self):
        total = self.task_list.count()
        completed_count = 0
        for i in range(total):
            item = self.task_list.item(i)
            widget = self.task_list.itemWidget(item)
            if widget and widget.is_completed():
                completed_count += 1
                
        if self.current_lang == "ru":
            self.counter_label.setText(f"Задач: {total} (выполнено: {completed_count})")
        else:
            self.counter_label.setText(f"Tasks: {total} (completed: {completed_count})")
        
        if total > 0:
            percent = int((completed_count / total) * 100)
            self.progress_bar.setValue(percent)
        else:
            self.progress_bar.setValue(0)

    def update_session_timer(self):
        self.elapsed_seconds += 1
        minutes = self.elapsed_seconds // 60
        seconds = self.elapsed_seconds % 60
        hours = minutes // 60
        minutes = minutes % 60

        if hours > 0:
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            time_str = f"{minutes:02d}:{seconds:02d}"
            
        self.timer_label.setText(f"⏱️ {time_str}")

    def closeEvent(self, event):
        msg = QMessageBox(self)
        msg.setWindowTitle("Закрытие приложения" if self.current_lang == "ru" else "Closing Application")
        msg.setText("Что вы хотите сделать с приложением?" if self.current_lang == "ru" else "What would you like to do?")
        if self.tray_available:
            msg.setInformativeText("Вы можете свернуть его в системный трей или закрыть полностью." if self.current_lang == "ru" else "You can minimize it to the system tray or close completely.")
            tray_btn = msg.addButton("Свернуть в трей" if self.current_lang == "ru" else "Minimize to Tray", QMessageBox.ButtonRole.ActionRole)
        else:
            msg.setInformativeText("Системный трей недоступен. Вы можете закрыть приложение." if self.current_lang == "ru" else "The system tray is unavailable. You can close the application.")
            tray_btn = None
        close_btn = msg.addButton("Закрыть полностью" if self.current_lang == "ru" else "Close Completely", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg.addButton("Отмена" if self.current_lang == "ru" else "Cancel", QMessageBox.ButtonRole.RejectRole)
        
        msg.exec()
        clicked = msg.clickedButton()

        if tray_btn is not None and clicked == tray_btn:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Менеджер задач" if self.current_lang == "ru" else "Task Manager",
                "Приложение работает в фоновом режиме." if self.current_lang == "ru" else "Application is running in the background.",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
            logger.info("Приложение свернуто в системный трей.")
        elif clicked == close_btn:
            logger.info("Закрытие приложения пользователем...")
            self.tray_icon.hide()
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            w, h = self.width(), self.height()
            b = 8
            
            edge = None
            on_left = pos.x() < b
            on_right = pos.x() >= w - b
            on_top = pos.y() < b
            on_bottom = pos.y() >= h - b
            
            if on_top and on_left: edge = Qt.Edge.TopEdge | Qt.Edge.LeftEdge
            elif on_top and on_right: edge = Qt.Edge.TopEdge | Qt.Edge.RightEdge
            elif on_bottom and on_left: edge = Qt.Edge.BottomEdge | Qt.Edge.LeftEdge
            elif on_bottom and on_right: edge = Qt.Edge.BottomEdge | Qt.Edge.RightEdge
            elif on_top: edge = Qt.Edge.TopEdge
            elif on_bottom: edge = Qt.Edge.BottomEdge
            elif on_left: edge = Qt.Edge.LeftEdge
            elif on_right: edge = Qt.Edge.RightEdge
            
            if edge is not None:
                if self.windowHandle():
                    self.windowHandle().startSystemResize(edge)
                    event.accept()
                    return
            
            if pos.y() <= 50:
                child = self.childAt(pos)
                if not isinstance(child, (QPushButton, QLineEdit, QComboBox, QDateTimeEdit, QTextEdit, QCheckBox)):
                    if self.windowHandle() and not self.is_pinned:
                        self.windowHandle().startSystemMove()
                        event.accept()
                        return
                        
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        w, h = self.width(), self.height()
        b = 8
        
        on_left = pos.x() < b
        on_right = pos.x() >= w - b
        on_top = pos.y() < b
        on_bottom = pos.y() >= h - b
        
        if (on_top and on_left) or (on_bottom and on_right):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif (on_top and on_right) or (on_bottom and on_left):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif on_left or on_right:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif on_top or on_bottom:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
        super().mouseMoveEvent(event)

    def toggle_pin(self):
        geometry = self.geometry()
        if self.is_pinned:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
            self.is_pinned = False
            self.locked_pos = None
            self.pin_button.setStyleSheet("")
            logger.info("Окно откреплено поверх остальных окон.")
        else:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.is_pinned = True
            self.locked_pos = self.pos()
            self.pin_button.setStyleSheet("background-color: #1f6feb; border: 1px solid #388bfd; border-radius: 16px; color: white;")
            logger.info("Окно закреплено поверх остальных окон.")
        self.show()
        self.setGeometry(geometry)

    def moveEvent(self, event):
        if self.is_pinned and self.locked_pos:
            self.move(self.locked_pos)
            event.ignore()
        else:
            super().moveEvent(event)

    def toggle_opacity(self):
        if self.is_transparent:
            self.setWindowOpacity(1.0)
            self.is_transparent = False
            logger.info("Прозрачность отключена (100%).")
        else:
            self.setWindowOpacity(self.custom_opacity)
            self.is_transparent = True
            logger.info(f"Включена прозрачность: {self.custom_opacity}")

    def open_settings(self):
        dialog = SettingsDialog(self.custom_opacity, self.current_lang, self.ai_api_key, DEFAULT_OPACITY, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.custom_opacity = dialog.get_opacity()
            self.current_lang = dialog.get_language()
            self.ai_api_key = dialog.get_api_key()
            
            self.settings.setValue("custom_opacity", self.custom_opacity)
            self.settings.setValue("current_language", self.current_lang)
            self.settings.setValue("ai_api_key", self.ai_api_key)
            logger.info(f"Настройки обновлены: прозрачность={self.custom_opacity}, язык={self.current_lang}, api_key_set={bool(self.ai_api_key)}")
            
            if self.is_transparent:
                self.setWindowOpacity(self.custom_opacity)
                
            self.retranslate_ui()

    def retranslate_ui(self):
        t = TRANSLATIONS[self.current_lang]
        
        self.label_new_task.setText(f"👤 {self.username}")
        self.task_input.setPlaceholderText(t["new_task_placeholder"])
        self.add_button.setText(t["add_btn"])
        self.ai_button.setText(t["ai_btn"])
        self.search_input.setPlaceholderText(t["search_placeholder"])
        
        current_cat_index = self.category_combo.currentIndex()
        self.category_combo.clear()
        self.category_combo.addItems(t["categories"])
        if 0 <= current_cat_index < self.category_combo.count():
            self.category_combo.setCurrentIndex(current_cat_index)
        
        self.category_filter_combo.clear()
        self.category_filter_combo.addItem(t["all_categories"])
        self.category_filter_combo.addItems(t["categories"])
        
        self.btn_all.setText(t["filter_all"])
        self.btn_active.setText(t["filter_active"])
        self.btn_completed.setText(t["filter_completed"])
        
        self.delete_button.setText(t["delete_btn"])
        self.clear_button.setText(t["clear_btn"])
        
        current_priority = self.priority_combo.currentText()
        self.priority_combo.clear()
        self.priority_combo.addItems(t["priorities"])
        
        self.update_stats()
        logger.info(f"Интерфейс переведен на язык: {self.current_lang}")

    def add_task(self):
        text = self.task_input.text().strip()
        category = self.category_combo.currentText()
        deadline = self.datetime_edit.dateTime().toString("yyyy-MM-dd HH:mm")
        priority = self.priority_combo.currentText()
        
        if text:
            self.send_task_to_server(text, priority, category, deadline, self.selected_shared_users, self.selected_shared_groups)
            self.task_input.clear()
            self.search_input.clear()
            self.category_filter_combo.setCurrentIndex(0)
            self.set_status_filter("all")
        else:
            logger.warning("Попытка добавить пустую задачу.")
            QMessageBox.warning(self, "Ошибка" if self.current_lang == "ru" else "Error", "Введите название задачи!" if self.current_lang == "ru" else "Enter task title!")

    def add_server_task_item(self, task_id, text, completed=False, priority="⚡ Средний", category="💻 Разработка", deadline="", author="", owner_id=None):
        item = QListWidgetItem()
        widget = TaskItemWidget(text, completed, priority, category, deadline, author)
        widget.task_id = task_id
        widget.owner_id = owner_id if owner_id is not None else self.user_id
        
        self.task_list.addItem(item)
        self.task_list.setItemWidget(item, widget)
        item.setSizeHint(QSize(self.task_list.viewport().width(), widget.height()))
        
        # Плавная анимация появления (Fade-In)
        opacity_effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(opacity_effect)
        anim = QPropertyAnimation(opacity_effect, b"opacity")
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        
        if not hasattr(self, "_anim_pool"):
            self._anim_pool = []
        self._anim_pool.append((anim, opacity_effect))

    def load_tasks(self, quiet=False):
        """Загрузка задач текущего пользователя и тех, которыми с ним поделились"""
        self._tasks_generation += 1
        generation = self._tasks_generation
        run_async(
            client.list_tasks,
            lambda data: self._tasks_loaded(generation, data),
            lambda error: self._tasks_failed(generation, error, quiet),
        )

    def _tasks_loaded(self, generation, data):
        if generation != self._tasks_generation:
            return  # a newer load superseded this answer
        self.task_list.clear()
        logger.info(f"Загружено задач для {self.username}: {len(data)}")
        for item_data in data:
            task_author = item_data.get("author_username", "")
            if task_author == self.username:
                task_author = ""

            self.add_server_task_item(
                task_id=item_data["id"],
                text=item_data["title"],
                completed=bool(item_data["status"]),
                priority=item_data["priority"],
                category=item_data["category"],
                deadline=item_data["deadline"],
                author=task_author,
                owner_id=item_data["user_id"]
            )
        self.update_stats()
        self.apply_filters()

    def _tasks_failed(self, generation, error, quiet):
        if generation != self._tasks_generation or quiet:
            logger.error(f"Не удалось загрузить задачи: {error}")
            return
        self._request_failed(error, "Не удалось загрузить задачи")

    def _find_row(self, task_id):
        for i in range(self.task_list.count()):
            widget = self.task_list.itemWidget(self.task_list.item(i))
            if widget is not None and getattr(widget, "task_id", None) == task_id:
                return i
        return -1

    def save_tasks(self):
        pass

    def delete_task(self):
        row = self.task_list.currentRow()
        if row >= 0:
            item = self.task_list.item(row)
            widget = self.task_list.itemWidget(item)
            task_id = getattr(widget, "task_id", None)
            if getattr(widget, "owner_id", self.user_id) != self.user_id:
                QMessageBox.warning(
                    self,
                    "Недостаточно прав" if self.current_lang == "ru" else "Not allowed",
                    "Удалить задачу может только её владелец." if self.current_lang == "ru" else "Only the task owner can delete it."
                )
                return
            
            answer = QMessageBox.question(
                self,
                "Подтверждение" if self.current_lang == "ru" else "Confirmation",
                "Удалить выбранную задачу?" if self.current_lang == "ru" else "Delete selected task?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if answer == QMessageBox.StandardButton.Yes:
                if task_id is None:
                    self.task_list.takeItem(row)
                    self.update_stats()
                    self.apply_filters()
                    return
                if task_id in self._deleting_ids:
                    return
                self._deleting_ids.add(task_id)
                run_async(
                    lambda: client.delete_task(task_id),
                    lambda _result: self._task_deleted(task_id),
                    lambda error: self._delete_failed(error, task_id),
                )
        else:
            logger.warning("Попытка удаления без выбора задачи.")
            QMessageBox.warning(self, "Ошибка" if self.current_lang == "ru" else "Error", "Выберите задачу для удаления!" if self.current_lang == "ru" else "Select a task to delete!")

    def _task_deleted(self, task_id):
        self._deleting_ids.discard(task_id)
        logger.info(f"Задача ID {task_id} удалена с сервера")
        row = self._find_row(task_id)
        if row >= 0:
            self.task_list.takeItem(row)
        self.update_stats()
        self.apply_filters()

    def _delete_failed(self, error, task_id):
        self._deleting_ids.discard(task_id)
        self._request_failed(error, "Не удалось удалить задачу с сервера")

    def clear_tasks(self):
        """Удалить завершённые задачи, владельцем которых является пользователь.

        Активные задачи и чужие общие задачи не затрагиваются, а в вопросе
        подтверждения указано точное число удаляемых задач.
        """
        ru = self.current_lang == "ru"
        completed_rows = []
        for i in range(self.task_list.count() - 1, -1, -1):
            widget = self.task_list.itemWidget(self.task_list.item(i))
            if (
                widget
                and widget.is_completed()
                and getattr(widget, "owner_id", self.user_id) == self.user_id
            ):
                completed_rows.append(i)

        if not completed_rows:
            QMessageBox.information(
                self,
                "Информация" if ru else "Information",
                "Нет завершённых задач для очистки." if ru else "There are no completed tasks to clear.",
            )
            return

        count = len(completed_rows)
        answer = QMessageBox.question(
            self,
            "Подтверждение" if ru else "Confirmation",
            (
                f"Удалить завершённые задачи: {count}?\nЭто действие нельзя отменить."
                if ru
                else f"Delete completed tasks: {count}?\nThis cannot be undone."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        task_ids = []
        for i in completed_rows:
            widget = self.task_list.itemWidget(self.task_list.item(i))
            task_id = getattr(widget, "task_id", None)
            if task_id is None:
                self.task_list.takeItem(i)  # never reached the server (rows go bottom-up)
            else:
                task_ids.append(task_id)
        if not task_ids:
            self.update_stats()
            self.apply_filters()
            return

        self._deleting_ids.update(task_ids)
        run_async(
            lambda: clear_completed(client, task_ids),
            lambda result: self._tasks_cleared(task_ids, *result),
            lambda error: self._cleared_failed(task_ids, error),
        )

    def _tasks_cleared(self, task_ids, deleted, failed):
        self._deleting_ids.difference_update(task_ids)
        for task_id in deleted:
            row = self._find_row(task_id)
            if row >= 0:
                self.task_list.takeItem(row)
        self.update_stats()
        self.apply_filters()
        if failed:
            ru = self.current_lang == "ru"
            QMessageBox.warning(
                self,
                "Ошибка" if ru else "Error",
                f"Не удалось удалить задач: {len(failed)}" if ru else f"Could not delete tasks: {len(failed)}",
            )

    def _cleared_failed(self, task_ids, error):
        self._deleting_ids.difference_update(task_ids)
        self._request_failed(error, "Не удалось очистить задачи")
