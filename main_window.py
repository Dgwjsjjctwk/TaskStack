import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QLineEdit, QPushButton, 
    QListWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QListWidgetItem,
    QDialog, QSlider, QComboBox, QProgressBar, QDateEdit, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, QSettings, QPoint, QTimer, QDate
from PyQt6.QtGui import QColor, QIcon
from config import ORGANIZATION_NAME, APPLICATION_NAME, DEFAULT_OPACITY, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT, CATEGORIES

logger = logging.getLogger("MainWindow")

class TaskItemWidget(QWidget):
    """Кастомный виджет задачи с приоритетом, категорией, дедлайном и статусом"""
    def __init__(self, text, completed=False, priority="⚡ Средний", category="📌 Прочее", deadline=""):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        self.priority = priority
        self.category = category
        self.deadline = deadline
        
        # Эмодзи приоритета
        self.priority_label = QLabel(priority.split()[0])
        self.priority_label.setStyleSheet("font-size: 14px;")
        
        # Метка категории
        self.cat_label = QLabel(f"[{category}]")
        self.cat_label.setStyleSheet("color: #8b949e; font-size: 12px;")

        # Текст задачи
        self.label = QLabel(text)
        
        # Дедлайн
        self.deadline_label = QLabel()
        self.update_deadline_style(completed)
        
        if completed:
            font = self.label.font()
            font.setStrikeOut(True)
            self.label.setFont(font)
            self.label.setStyleSheet("color: #9ca3af;")
        else:
            self.label.setStyleSheet("color: #f3f4f6;")
        
        self.green_btn = QPushButton("")
        self.green_btn.setObjectName("GreenBtn")
        self.green_btn.setFixedSize(24, 24)
        self.green_btn.clicked.connect(self.set_completed)
        
        self.red_btn = QPushButton("")
        self.red_btn.setObjectName("RedBtn")
        self.red_btn.setFixedSize(24, 24)
        self.red_btn.clicked.connect(self.set_uncompleted)
        
        layout.addWidget(self.priority_label)
        layout.addWidget(self.cat_label)
        layout.addWidget(self.label)
        if deadline:
            layout.addWidget(self.deadline_label)
        layout.addStretch()
        layout.addWidget(self.green_btn)
        layout.addWidget(self.red_btn)
        
    def update_deadline_style(self, completed):
        if not self.deadline:
            return
        self.deadline_label.setText(f"📅 {self.deadline}")
        if not completed:
            # Проверяем, просрочен ли дедлайн
            due_date = QDate.fromString(self.deadline, "yyyy-MM-dd")
            if due_date.isValid() and due_date < QDate.currentDate():
                self.deadline_label.setStyleSheet("color: #da3633; font-size: 11px; font-weight: bold;")
                self.deadline_label.setToolTip("Просрочено!")
            else:
                self.deadline_label.setStyleSheet("color: #8b949e; font-size: 11px;")
                self.deadline_label.setToolTip("Срок выполнения")
        else:
            self.deadline_label.setStyleSheet("color: #6e7681; font-size: 11px;")

    def get_text(self):
        return self.label.text()
        
    def get_priority(self):
        return self.priority

    def get_category(self):
        return self.category

    def get_deadline(self):
        return self.deadline

    def is_completed(self):
        return self.label.font().strikeOut()
        
    def set_completed(self):
        font = self.label.font()
        font.setStrikeOut(True)
        self.label.setFont(font)
        self.label.setStyleSheet("color: #9ca3af;")
        self.update_deadline_style(completed=True)
        logger.info(f"Задача отмечена как выполненная: '{self.get_text()}'")
        window = self.window()
        if hasattr(window, "update_stats"):
            window.update_stats()
            window.apply_filters()
        
    def set_uncompleted(self):
        font = self.label.font()
        font.setStrikeOut(False)
        self.label.setFont(font)
        self.label.setStyleSheet("color: #f3f4f6;")
        self.update_deadline_style(completed=False)
        logger.info(f"Задача возвращена в активные: '{self.get_text()}'")
        window = self.window()
        if hasattr(window, "update_stats"):
            window.update_stats()
            window.apply_filters()


class SettingsDialog(QDialog):
    def __init__(self, current_opacity, default_opacity=DEFAULT_OPACITY, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.resize(300, 180)
        
        self.default_value = int(default_opacity * 100)
        layout = QVBoxLayout(self)
        
        self.label = QLabel(f"Степень полупрозрачности: {int(current_opacity * 100)}%")
        layout.addWidget(self.label)
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(20, 100)
        self.slider.setValue(int(current_opacity * 100))
        self.slider.valueChanged.connect(self.slider_changed)
        layout.addWidget(self.slider)
        
        self.reset_btn = QPushButton("Сбросить по умолчанию")
        self.reset_btn.clicked.connect(self.reset_to_default)
        layout.addWidget(self.reset_btn)
        
        self.save_btn = QPushButton("Готово")
        self.save_btn.clicked.connect(self.accept)
        layout.addWidget(self.save_btn)
        
    def slider_changed(self, value):
        self.label.setText(f"Степень полупрозрачности: {value}%")
        
    def reset_to_default(self):
        self.slider.setValue(self.default_value)
        
    def get_opacity(self):
        return self.slider.value() / 100.0


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Менеджер задач")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(450, 400)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMouseTracking(True)

        self.settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
        saved_opacity = self.settings.value("custom_opacity", DEFAULT_OPACITY, type=float)
        self.custom_opacity = saved_opacity
        logger.info(f"Загружена настройка прозрачности: {self.custom_opacity}")

        self.is_transparent = False
        self.is_pinned = False
        self.locked_pos = None
        
        self.current_filter = "all"
        self.current_category_filter = "Все категории"
        self.elapsed_seconds = 0

        self.init_ui()
        self.init_tray()
        self.connect_signals()
        
        self.load_tasks()
        self.update_stats()

        self.session_timer = QTimer(self)
        self.session_timer.timeout.connect(self.update_session_timer)
        self.session_timer.start(1000)

    def init_tray(self):
        """Инициализация системного трея"""
        self.tray_icon = QSystemTrayIcon(self)
        # Используем текущую иконку окна для трея
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

    def tray_icon_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_from_tray()

    def force_close(self):
        """Полный выход из приложения из трея"""
        logger.info("Принудительное закрытие из трея...")
        self.save_tasks()
        self.tray_icon.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        top_layout = QHBoxLayout()
        self.label_new_task = QLabel("  Менеджер задач")
        
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
        
        top_layout.addWidget(self.label_new_task)
        top_layout.addStretch()
        top_layout.addWidget(self.pin_button)
        top_layout.addWidget(self.opacity_button)
        top_layout.addWidget(self.settings_button)
        top_layout.addWidget(self.minimize_button)
        top_layout.addWidget(self.close_button)

        # Строка добавления задачи: Название + Категория + Дедлайн + Приоритет + Кнопка
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("Название новой задачи...")

        self.category_combo = QComboBox()
        self.category_combo.addItems(CATEGORIES)
        self.category_combo.setFixedWidth(130)

        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setFixedWidth(105)

        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["⚡ Средний", "🔥 Высокий", "☕ Низкий"])
        self.priority_combo.setFixedWidth(115)

        self.add_button = QPushButton("Добавить")
        self.add_button.setObjectName("AddButton")

        input_layout = QHBoxLayout()
        input_layout.addWidget(self.task_input)
        input_layout.addWidget(self.category_combo)
        input_layout.addWidget(self.date_edit)
        input_layout.addWidget(self.priority_combo)
        input_layout.addWidget(self.add_button)

        # Поиск и фильтр по категориям
        search_filter_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Поиск по задачам...")

        self.category_filter_combo = QComboBox()
        self.category_filter_combo.addItem("Все категории")
        self.category_filter_combo.addItems(CATEGORIES)
        self.category_filter_combo.setFixedWidth(150)

        search_filter_layout.addWidget(self.search_input)
        search_filter_layout.addWidget(self.category_filter_combo)

        # Панель статус-фильтров (Все, Активные, Завершённые)
        status_filter_layout = QHBoxLayout()
        self.btn_all = QPushButton("Все")
        self.btn_all.setObjectName("FilterBtn")
        self.btn_all.setProperty("active", "true")
        
        self.btn_active = QPushButton("Активные")
        self.btn_active.setObjectName("FilterBtn")
        self.btn_active.setProperty("active", "false")
        
        self.btn_completed = QPushButton("Завершённые")
        self.btn_completed.setObjectName("FilterBtn")
        self.btn_completed.setProperty("active", "false")

        status_filter_layout.addWidget(self.btn_all)
        status_filter_layout.addWidget(self.btn_active)
        status_filter_layout.addWidget(self.btn_completed)
        
        self.task_list = QListWidget()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.delete_button = QPushButton("🗑 Удалить")
        self.delete_button.setObjectName("ActionBtn")
        
        self.clear_button = QPushButton("🧹 Очистить всё")
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
        main_layout.addLayout(input_layout)
        main_layout.addLayout(search_filter_layout)
        main_layout.addLayout(status_filter_layout)
        main_layout.addWidget(self.task_list)
        main_layout.addWidget(self.progress_bar)
        main_layout.addLayout(bottom_layout)

    def connect_signals(self):
        self.add_button.clicked.connect(self.add_task)
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
        self.close_button.clicked.connect(self.close) # Вызовет closeEvent с диалогом

        self.delete_button.clicked.connect(self.delete_task)
        self.clear_button.clicked.connect(self.clear_tasks)

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
                
                cat_match = (selected_cat == "Все категории") or (cat == selected_cat)
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
                
        self.counter_label.setText(f"Задач: {total} (выполнено: {completed_count})")
        
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
        """Перехват закрытия окна: показываем диалог выбора (свернуть в трей / закрыть)"""
        msg = QMessageBox(self)
        msg.setWindowTitle("Закрытие приложения")
        msg.setText("Что вы хотите сделать с приложением?")
        msg.setInformativeText("Вы можете свернуть его в системный трей или закрыть полностью.")
        
        tray_btn = msg.addButton("Свернуть в трей", QMessageBox.ButtonRole.ActionRole)
        close_btn = msg.addButton("Закрыть полностью", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        
        msg.exec()
        clicked = msg.clickedButton()

        if clicked == tray_btn:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Менеджер задач сворнули",
                "Приложение работает в фоновом режиме. Кликните по иконке в трее, чтобы открыть его.",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
            logger.info("Приложение свернуто в системный трей.")
        elif clicked == close_btn:
            logger.info("Закрытие приложения пользователем. Сохранение данных...")
            self.save_tasks()
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
                if not isinstance(child, (QPushButton, QLineEdit, QComboBox, QDateEdit)):
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
        dialog = SettingsDialog(self.custom_opacity, DEFAULT_OPACITY, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.custom_opacity = dialog.get_opacity()
            self.settings.setValue("custom_opacity", self.custom_opacity)
            logger.info(f"Изменена и сохранена новая прозрачность в настройках: {self.custom_opacity}")
            if self.is_transparent:
                self.setWindowOpacity(self.custom_opacity)

    def add_task(self):
        text = self.task_input.text().strip()
        category = self.category_combo.currentText()
        deadline = self.date_edit.date().toString("yyyy-MM-dd")
        priority = self.priority_combo.currentText()
        
        if text:
            self.add_task_item(text, completed=False, priority=priority, category=category, deadline=deadline)
            logger.info(f"Добавлена новая задача: '{text}' [Категория: {category}, Дедлайн: {deadline}, Приоритет: {priority}]")
            self.task_input.clear()
            self.search_input.clear()
            self.category_filter_combo.setCurrentIndex(0)
            self.set_status_filter("all")
            self.update_stats()
        else:
            logger.warning("Попытка добавить пустую задачу.")
            QMessageBox.warning(self, "Ошибка", "Введите название задачи!")

    def add_task_item(self, text, completed=False, priority="⚡ Средний", category="📌 Прочее", deadline=""):
        item = QListWidgetItem()
        widget = TaskItemWidget(text, completed, priority, category, deadline)
        item.setSizeHint(widget.sizeHint())
        
        self.task_list.addItem(item)
        self.task_list.setItemWidget(item, widget)

    def load_tasks(self):
        texts = self.settings.value("tasks_texts", [], type=list)
        statuses = self.settings.value("tasks_statuses", [], type=list)
        priorities = self.settings.value("tasks_priorities", [], type=list)
        categories = self.settings.value("tasks_categories", [], type=list)
        deadlines = self.settings.value("tasks_deadlines", [], type=list)
        
        logger.info(f"Загрузка сохраненных задач из хранилища. Найдено записей: {len(texts)}")
        for i, text in enumerate(texts):
            status = statuses[i] if i < len(statuses) else 0
            if isinstance(status, bool):
                completed = status
            elif isinstance(status, (int, float)):
                completed = bool(status)
            elif isinstance(status, str):
                completed = status.lower() in ('true', '1', 'yes')
            else:
                completed = False
                
            priority = priorities[i] if i < len(priorities) else "⚡ Средний"
            category = categories[i] if i < len(categories) else "📌 Прочее"
            deadline = deadlines[i] if i < len(deadlines) else ""
            
            self.add_task_item(text, completed, priority, category, deadline)

    def save_tasks(self):
        texts, statuses, priorities, categories, deadlines = [], [], [], [], []
        for i in range(self.task_list.count()):
            item = self.task_list.item(i)
            widget = self.task_list.itemWidget(item)
            if widget:
                texts.append(widget.get_text())
                statuses.append(1 if widget.is_completed() else 0)
                priorities.append(widget.get_priority())
                categories.append(widget.get_category())
                deadlines.append(widget.get_deadline())
                
        self.settings.setValue("tasks_texts", texts)
        self.settings.setValue("tasks_statuses", statuses)
        self.settings.setValue("tasks_priorities", priorities)
        self.settings.setValue("tasks_categories", categories)
        self.settings.setValue("tasks_deadlines", deadlines)
        logger.info(f"Успешно сохранено задач в хранилище: {len(texts)}")

    def delete_task(self):
        row = self.task_list.currentRow()
        if row >= 0:
            item = self.task_list.item(row)
            widget = self.task_list.itemWidget(item)
            task_text = widget.get_text() if widget else "неизвестно"
            
            answer = QMessageBox.question(
                self,
                "Подтверждение",
                "Удалить выбранную задачу?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.task_list.takeItem(row)
                logger.info(f"Удалена задача: '{task_text}'")
                self.update_stats()
                self.apply_filters()
        else:
            logger.warning("Попытка удаления без выбора задачи.")
            QMessageBox.warning(self, "Ошибка", "Выберите задачу для удаления!")

    def clear_tasks(self):
        if self.task_list.count() > 0:
            answer = QMessageBox.question(
                self,
                "Подтверждение",
                "Вы уверены, что хотите очистить весь список?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if answer == QMessageBox.StandardButton.Yes:
                count = self.task_list.count()
                self.task_list.clear()
                self.search_input.clear()
                self.category_filter_combo.setCurrentIndex(0)
                self.set_status_filter("all")
                self.update_stats()
                logger.info(f"Очищен весь список задач. Удалено элементов: {count}")
        else:
            QMessageBox.warning(self, "Информация", "Список задач уже пуст!")