import os
import json
import uuid
from PySide6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
                               QFrame, QRubberBand, QGraphicsOpacityEffect, QSizePolicy,
                               QScrollArea, QDialog, QLineEdit, QListWidget, QListWidgetItem,
                               QStackedWidget, QMenu, QInputDialog)
from PySide6.QtCore import Qt, QUrl, QSize, QTimer, QSettings, QPropertyAnimation, QEasingCurve, Signal, QPoint, QRect, \
    QParallelAnimationGroup, QSequentialAnimationGroup
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QCursor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

from app.setting_panel import SettingPanel


# Animated plus/delete version: clean-pop v3


class HorizontalWheelScrollArea(QScrollArea):
    """
    A QScrollArea that scrolls horizontally in response to the mouse wheel.

    QScrollArea normally only scrolls vertically on wheel events — it has no
    built-in way to redirect that motion to a horizontal scrollbar. Since
    this bar only ever has horizontal content (the LLM buttons), we just
    take whatever wheel delta arrives and apply it to the horizontal
    scrollbar instead of the vertical one.
    """

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.angleDelta().x()
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - delta)
        event.accept()


class AddLLMDialog(QDialog):
    llm_selected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedSize(200, 250)
        self.setStyleSheet("""
            QDialog {
                background-color: #1f1f1f;
                border: 1px solid #333333;
                border-radius: 8px;
            }
            QLineEdit {
                background-color: #151515;
                border: 1px solid #333333;
                border-radius: 6px;
                color: white;
                padding: 6px 10px;
                font-family: "Segoe UI";
            }
            QListWidget {
                background-color: transparent;
                border: none;
                color: white;
                outline: none;
                font-family: "Segoe UI";
                margin-top: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #333333;
            }
            QListWidget::item:selected {
                background-color: #444444;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search LLMs...")
        self.search_bar.textChanged.connect(self.filter_list)
        layout.addWidget(self.search_bar)

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        layout.addWidget(self.list_widget)

        self.all_llms = [
            {"name": "ChatGPT", "url": "https://chatgpt.com"},
            {"name": "Claude", "url": "https://claude.ai"},
            {"name": "Gemini", "url": "https://gemini.google.com"},
            {"name": "Perplexity", "url": "https://perplexity.ai"},
            {"name": "DeepSeek", "url": "https://chat.deepseek.com"},
            {"name": "HuggingFace", "url": "https://huggingface.co/chat/"}
        ]
        self.populate_list(self.all_llms)

    def populate_list(self, llm_list):
        self.list_widget.clear()
        for llm in llm_list:
            item = QListWidgetItem(llm["name"])
            item.setData(Qt.UserRole, llm["url"])
            self.list_widget.addItem(item)

    def filter_list(self, text):
        filtered = [llm for llm in self.all_llms if text.lower() in llm["name"].lower()]
        self.populate_list(filtered)

    def on_item_clicked(self, item):
        name = item.text()
        url = item.data(Qt.UserRole)
        self.llm_selected.emit(name, url)
        self.accept()


class ChatPanel(QWidget):
    def __init__(self, bubble=None):
        super().__init__()

        self.bubble = bubble
        self.drag_position = None
        self.tab_animations = []

        self.resize_margin = 8  # Detects mouse when it is within 8 pixels of an edge
        self.resize_direction = None  # Tracks which edge or corner is being pulled

        # --- Resize throttling ---
        self.pending_geometry = None
        self.resize_timer = QTimer(self)
        self.resize_timer.setInterval(5)  # ~200 fps
        self.resize_timer.timeout.connect(self.apply_pending_geometry)

        self.setup_window()

        # 1. THIS MUST COME FIRST: It creates self.chatgpt_button, etc.
        self.create_widgets()

        self.setting_panel = SettingPanel()
        self.setting_panel.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )

        # Listen for the signal from the settings panel
        self.setting_panel.color_changed.connect(self.update_content_area_color)

        # --- NEW: Listen for the privacy clear data signal ---
        self.setting_panel.clear_data_requested.connect(self.clear_browsing_data)

        # 2. THIS MUST COME LAST: It puts the widgets into the layout
        self.create_layout()

    def save_setting(self, key, value):
        self.settings.setValue(key, value)
        self.settings.sync()

    def setup_window(self):
        self.setMinimumSize(400, 400)

        # Initialize QSettings and load the saved size
        self.settings = QSettings("MyLLMWidget", "ChatPanel")
        self.current_provider = self.settings.value("current_provider", "ChatGPT")
        self.current_provider_id = self.settings.value("current_provider_id", None)

        active_str = self.settings.value("active_llms")
        if active_str:
            self.active_llms = json.loads(active_str)
            migrated = False
            for llm in self.active_llms:
                if "id" not in llm:
                    llm["id"] = str(uuid.uuid4())
                    migrated = True
            if migrated:
                self.save_setting("active_llms", json.dumps(self.active_llms))
        else:
            self.active_llms = [
                {"id": str(uuid.uuid4()), "name": "ChatGPT", "url": "https://chatgpt.com"},
                {"id": str(uuid.uuid4()), "name": "Claude", "url": "https://claude.ai"},
                {"id": str(uuid.uuid4()), "name": "Gemini", "url": "https://gemini.google.com"}
            ]

        saved_size = self.settings.value("window_size")
        if saved_size:
            self.resize(saved_size)
        else:
            self.resize(900, 700)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setMouseTracking(True)

        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
                color: #ececec;
                font-family: "Segoe UI";
            }

            QFrame#mainContainer {
                background-color: rgba(15, 15, 15, 180);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 24px;
            }

            QLabel#title {
                font-size: 20px;
                font-weight: 600;
            }

            QPushButton {
                background-color: #303030;
                color: #ececec;
                border: 1px solid #444444;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 14px;
            }

            QPushButton:hover {
                background-color: #3a3a3a;
            }

            QPushButton#closeButton {
                background-color: transparent;
                border: none;
                color: #b4b4b4;
                font-size: 16px; 
                font-weight: 100;
                padding: 0px; 
                margin: 0px;
            }

            QPushButton#closeButton:hover {
                color: white;
                background-color: #333333;
                border-radius: 8px;
            }

            QPushButton#addButton {
                font-size: 20px;
                font-weight: bold;
                padding: 0px;
                padding-bottom: 6px; 
            }

            QPushButton#settingsButton {
                background-color: transparent;
                border: none;
                border-radius: 8px;
            }

            QPushButton#settingsButton:hover {
                background-color: #333333;
            }
        """)

    def create_widgets(self):
        self.container = QFrame()
        self.container.setObjectName("mainContainer")
        self.container.setMouseTracking(True)

        self.scroll_area = HorizontalWheelScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFixedHeight(45)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
        """)

        self.llm_container = QWidget()
        self.llm_layout = QHBoxLayout(self.llm_container)
        self.llm_layout.setContentsMargins(0, 0, 0, 0)
        self.llm_layout.setSpacing(10)

        self.add_button = QPushButton("+")
        self.add_button.setObjectName("addButton")
        self.add_button.setFixedSize(26, 26)
        self.add_button.clicked.connect(self.open_add_llm_menu)

        self.scroll_area.setWidget(self.llm_container)
        self.render_active_llms()

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(32, 32)
        self.close_button.clicked.connect(self.close_panel)

        self.settings_button = QPushButton()
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setFixedSize(32, 32)
        self.settings_button.clicked.connect(self.open_settings)

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(project_root, "assets", "gearsettings.png")

        icon_pixmap = QPixmap(icon_path)
        if not icon_pixmap.isNull():
            painter = QPainter(icon_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(icon_pixmap.rect(), QColor("#b4b4b4"))
            painter.end()

            self.settings_button.setIcon(QIcon(icon_pixmap))
            self.settings_button.setIconSize(QSize(20, 20))

        self.browser = QWebEngineView()

        browser_policy = self.browser.sizePolicy()
        browser_policy.setHorizontalPolicy(QSizePolicy.Expanding)
        browser_policy.setVerticalPolicy(QSizePolicy.Expanding)
        browser_policy.setRetainSizeWhenHidden(True)
        self.browser.setSizePolicy(browser_policy)

        self.profile = QWebEngineProfile("llm_profile", self.browser)

        storage_path = os.path.join(project_root, "session_data")
        self.profile.setPersistentStoragePath(storage_path)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

        self.page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(self.page)

        start_url = "https://chatgpt.com"
        match = None
        if self.current_provider_id:
            match = next((llm for llm in self.active_llms if llm.get("id") == self.current_provider_id), None)
        if match is None:
            match = next((llm for llm in self.active_llms if llm["name"] == self.current_provider), None)
        if match:
            start_url = match["url"]
        self.browser.setUrl(QUrl(start_url))

    def render_active_llms(self):
        self.llm_buttons = {}

        while self.llm_layout.count():
            item = self.llm_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        for llm in self.active_llms:
            btn = QPushButton(llm["name"])
            btn.clicked.connect(
                lambda checked=False, name=llm["name"], url=llm["url"], llm_id=llm["id"]:
                self.open_llm_url(name, url, llm_id)
            )

            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, button=btn, llm_id=llm["id"]:
                self.show_llm_context_menu(button, llm_id)
            )

            self.llm_buttons[llm["id"]] = btn
            self.llm_layout.addWidget(btn, alignment=Qt.AlignVCenter)

        self.llm_layout.addWidget(self.add_button, alignment=Qt.AlignVCenter)
        self.llm_layout.addStretch()

    def show_llm_context_menu(self, button, llm_id):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1f1f1f; border: 1px solid #333333; border-radius: 8px; padding: 4px; color: #ececec; }
            QMenu::item { padding: 6px 16px; border-radius: 4px; }
            QMenu::item:selected { background-color: #333333; }
            QMenu::separator { height: 1px; background: #333333; margin: 4px 8px; }
        """)

        rename_action = menu.addAction("Rename")
        duplicate_action = menu.addAction("Duplicate")
        default_action = menu.addAction("Set as Default")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        if llm_id == self.current_provider_id:
            default_action.setEnabled(False)
            default_action.setText("Set as Default ✓")

        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

        if chosen == rename_action:
            self.rename_llm_entry(llm_id)
        elif chosen == duplicate_action:
            self.duplicate_llm_entry(llm_id)
        elif chosen == default_action:
            self.set_default_llm_entry(llm_id)
        elif chosen == delete_action:
            self.delete_llm_entry(llm_id)

    def _find_llm_index(self, llm_id):
        for i, llm in enumerate(self.active_llms):
            if llm["id"] == llm_id: return i
        return -1

    def rename_llm_entry(self, llm_id):
        index = self._find_llm_index(llm_id)
        if index == -1: return

        old_name = self.active_llms[index]["name"]
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        new_name = new_name.strip()

        if not ok or not new_name or new_name == old_name: return

        self.active_llms[index]["name"] = new_name

        if llm_id == self.current_provider_id:
            self.current_provider = new_name
            self.save_setting("current_provider", self.current_provider)

        self.save_setting("active_llms", json.dumps(self.active_llms))
        self.render_active_llms()

    def duplicate_llm_entry(self, llm_id):
        index = self._find_llm_index(llm_id)
        if index == -1: return

        original = self.active_llms[index]
        copy_entry = {"id": str(uuid.uuid4()), "name": original["name"], "url": original["url"]}
        self.active_llms.insert(index + 1, copy_entry)

        self.save_setting("active_llms", json.dumps(self.active_llms))
        self.render_active_llms()

    def set_default_llm_entry(self, llm_id):
        index = self._find_llm_index(llm_id)
        if index == -1: return

        entry = self.active_llms[index]
        self.current_provider = entry["name"]
        self.current_provider_id = entry["id"]
        self.save_setting("current_provider", self.current_provider)
        self.save_setting("current_provider_id", self.current_provider_id)

        self.render_active_llms()

    def delete_llm_entry(self, llm_id):
        index = self._find_llm_index(llm_id)
        if index == -1:
            return

        self.play_delete_pop_animation(llm_id)

    def finish_delete_llm_entry(self, llm_id):
        index = self._find_llm_index(llm_id)
        if index == -1:
            self.render_active_llms()
            return

        deleting_current = llm_id == self.current_provider_id
        del self.active_llms[index]

        if deleting_current:
            if self.active_llms:
                fallback = self.active_llms[0]
                self.current_provider = fallback["name"]
                self.current_provider_id = fallback["id"]
                self.browser.setUrl(QUrl(fallback["url"]))
            else:
                self.current_provider = "ChatGPT"
                self.current_provider_id = None
            self.save_setting("current_provider", self.current_provider)
            self.save_setting("current_provider_id", self.current_provider_id)

        self.save_setting("active_llms", json.dumps(self.active_llms))
        self.render_active_llms()

    def play_delete_pop_animation(self, llm_id):
        """
        Delete animation with delayed layout movement:
        - the real button stays in the layout as an invisible spacer
        - a ghost tab does the pop/shrink/fade animation on top
        - after the ghost fully disappears, waits briefly
        - then the real button width collapses, making the right tab slide over
        """
        button = self.llm_buttons.get(llm_id)

        if not button:
            self.finish_delete_llm_entry(llm_id)
            return

        button_rect = self.widget_rect_in_panel(button)
        center = button_rect.center()
        start_width = button.width()
        start_height = button.height()

        # Keep the real button in the layout so nothing moves yet.
        button.setEnabled(False)
        button.setMinimumWidth(start_width)
        button.setMaximumWidth(start_width)
        button.setMinimumHeight(start_height)
        button.setMaximumHeight(start_height)

        button_opacity = QGraphicsOpacityEffect(button)
        button.setGraphicsEffect(button_opacity)
        button_opacity.setOpacity(0.0)

        # Ghost is what visually pops/disappears.
        ghost = QPushButton(button.text(), self)
        ghost.setGeometry(button_rect)
        ghost.setStyleSheet("""
            QPushButton {
                background-color: #303030;
                color: #ececec;
                border: 1px solid #444444;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 14px;
                font-family: "Segoe UI";
            }
        """)
        ghost.show()
        ghost.raise_()

        ghost_opacity = QGraphicsOpacityEffect(ghost)
        ghost.setGraphicsEffect(ghost_opacity)

        start_rect = QRect(button_rect)

        pop_rect = QRect(
            start_rect.x() - 4,
            start_rect.y() - 3,
            start_rect.width() + 8,
            start_rect.height() + 6
        )

        shrink_rect = QRect(
            center.x() - 2,
            center.y() - 2,
            4,
            4
        )

        pop_anim = QPropertyAnimation(ghost, b"geometry")
        pop_anim.setDuration(115)
        pop_anim.setStartValue(start_rect)
        pop_anim.setEndValue(pop_rect)
        pop_anim.setEasingCurve(QEasingCurve.OutCubic)

        shrink_anim = QPropertyAnimation(ghost, b"geometry")
        shrink_anim.setDuration(230)
        shrink_anim.setStartValue(pop_rect)
        shrink_anim.setEndValue(shrink_rect)
        shrink_anim.setEasingCurve(QEasingCurve.InBack)

        fade_anim = QPropertyAnimation(ghost_opacity, b"opacity")
        fade_anim.setDuration(40)
        fade_anim.setStartValue(1.0)
        fade_anim.setEndValue(0.0)
        fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        shrink_group = QParallelAnimationGroup(self)
        shrink_group.addAnimation(shrink_anim)
        shrink_group.addAnimation(fade_anim)

        # Small water-like particle pop.
        particle_group = QParallelAnimationGroup(self)
        pop_offsets = [
            QPoint(-18, -8), QPoint(-12, 12), QPoint(15, -11),
            QPoint(19, 7), QPoint(-2, -18), QPoint(5, 17)
        ]
        pop_dots = []

        for i, offset in enumerate(pop_offsets):
            dot, dot_opacity = self.make_splash_dot(center, 4 if i % 2 else 5)
            pop_dots.append(dot)

            end_rect = QRect(
                center.x() + offset.x(),
                center.y() + offset.y(),
                1,
                1
            )

            dot_move = QPropertyAnimation(dot, b"geometry")
            dot_move.setDuration(210)
            dot_move.setStartValue(dot.geometry())
            dot_move.setEndValue(end_rect)
            dot_move.setEasingCurve(QEasingCurve.OutCubic)

            dot_fade = QPropertyAnimation(dot_opacity, b"opacity")
            dot_fade.setDuration(210)
            dot_fade.setStartValue(1.0)
            dot_fade.setEndValue(0.0)
            dot_fade.setEasingCurve(QEasingCurve.OutQuad)

            particle_group.addAnimation(dot_move)
            particle_group.addAnimation(dot_fade)

        # This is the actual slide-over part.
        # It only starts after the tab has fully disappeared, plus a tiny pause.
        collapse_min = QPropertyAnimation(button, b"minimumWidth")
        collapse_min.setDuration(320)
        collapse_min.setStartValue(start_width)
        collapse_min.setEndValue(0)
        collapse_min.setEasingCurve(QEasingCurve.OutCubic)

        collapse_max = QPropertyAnimation(button, b"maximumWidth")
        collapse_max.setDuration(320)
        collapse_max.setStartValue(start_width)
        collapse_max.setEndValue(0)
        collapse_max.setEasingCurve(QEasingCurve.OutCubic)

        collapse_group = QParallelAnimationGroup(self)
        collapse_group.addAnimation(collapse_min)
        collapse_group.addAnimation(collapse_max)
#
        def finish_pop():
            shrink_group.start()
            particle_group.start()

        def start_slide_after_pause():
            ghost.deleteLater()
            for dot in pop_dots:
                dot.deleteLater()
            QTimer.singleShot(180, collapse_group.start)

        def finish_delete():
            button.setGraphicsEffect(None)
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
            button.setMinimumHeight(0)
            button.setMaximumHeight(16777215)
            self.finish_delete_llm_entry(llm_id)

        pop_anim.finished.connect(finish_pop)
        shrink_group.finished.connect(start_slide_after_pause)
        collapse_group.finished.connect(finish_delete)

        self.tab_animations.append(pop_anim)
        self.tab_animations.append(shrink_group)
        self.tab_animations.append(particle_group)
        self.tab_animations.append(collapse_group)

        pop_anim.start()

    def open_add_llm_menu(self):
        dialog = AddLLMDialog(self)
        dialog.llm_selected.connect(self.add_llm_to_bar)

        button_pos = self.add_button.mapToGlobal(QPoint(0, self.add_button.height()))
        dialog.move(button_pos.x() - (dialog.width() // 2), button_pos.y() + 5)
        dialog.exec()

    def add_llm_to_bar(self, name, url):
        if any(llm["name"] == name for llm in self.active_llms):
            return

        new_llm = {"id": str(uuid.uuid4()), "name": name, "url": url}
        self.play_add_llm_animation(new_llm)

    def widget_rect_in_panel(self, widget):
        top_left = widget.mapTo(self, QPoint(0, 0))
        return QRect(top_left, widget.size())

    def play_add_llm_animation(self, new_llm):
        """
        Drop/add animation from the other version:
        - a small droplet falls into the plus button
        - the new tab materializes from the plus position
        - the plus button slides to the right with a soft OutBack bounce
        """
        old_plus_rect = self.widget_rect_in_panel(self.add_button)
        plus_center = old_plus_rect.center()

        self.add_button.setEnabled(False)

        drop = QLabel(self)
        drop.setFixedSize(14, 14)
        drop.setStyleSheet("""
            QLabel {
                background-color: #ececec;
                border-radius: 7px;
            }
        """)

        drop_start = QRect(plus_center.x() - 7, plus_center.y() - 70, 14, 14)
        drop_end = QRect(plus_center.x() - 4, plus_center.y() - 4, 8, 8)

        drop.setGeometry(drop_start)
        drop.show()
        drop.raise_()

        opacity = QGraphicsOpacityEffect(drop)
        drop.setGraphicsEffect(opacity)

        drop_move = QPropertyAnimation(drop, b"geometry")
        drop_move.setDuration(280)
        drop_move.setStartValue(drop_start)
        drop_move.setEndValue(drop_end)
        drop_move.setEasingCurve(QEasingCurve.InCubic)

        drop_fade = QPropertyAnimation(opacity, b"opacity")
        drop_fade.setDuration(280)
        drop_fade.setStartValue(1.0)
        drop_fade.setEndValue(0.15)
        drop_fade.setEasingCurve(QEasingCurve.InCubic)

        drop_group = QParallelAnimationGroup(self)
        drop_group.addAnimation(drop_move)
        drop_group.addAnimation(drop_fade)

        def after_drop():
            drop.deleteLater()
            self.active_llms.append(new_llm)
            self.save_setting("active_llms", json.dumps(self.active_llms))
            self.render_active_llms()
            QTimer.singleShot(0, lambda: self.play_plus_to_tab_animation(old_plus_rect, new_llm["id"]))

        drop_group.finished.connect(after_drop)
        self.tab_animations.append(drop_group)
        drop_group.start()

    def make_splash_dot(self, center, size=7):
        dot = QLabel(self)
        dot.setFixedSize(size, size)
        radius = size // 2
        dot.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(170, 125, 255, 220);
                border: 1px solid rgba(235, 225, 255, 180);
                border-radius: {radius}px;
            }}
        """)
        dot.move(center.x() - radius, center.y() - radius)
        dot.show()
        dot.raise_()
        opacity = QGraphicsOpacityEffect(dot)
        dot.setGraphicsEffect(opacity)
        return dot, opacity

    def play_water_splash(self, old_plus_rect, plus_center, new_llm):
        # Ripple ring + small droplets shooting out = the "plash" feeling.
        ripple = QLabel(self)
        ripple.setStyleSheet("""
            QLabel {
                background-color: transparent;
                border: 2px solid rgba(165, 120, 255, 180);
                border-radius: 5px;
            }
        """)
        ripple_start = QRect(plus_center.x() - 5, plus_center.y() - 5, 10, 10)
        ripple_end = QRect(plus_center.x() - 28, plus_center.y() - 28, 56, 56)
        ripple.setGeometry(ripple_start)
        ripple.show()
        ripple.raise_()

        ripple_opacity = QGraphicsOpacityEffect(ripple)
        ripple.setGraphicsEffect(ripple_opacity)

        ripple_grow = QPropertyAnimation(ripple, b"geometry")
        ripple_grow.setDuration(240)
        ripple_grow.setStartValue(ripple_start)
        ripple_grow.setEndValue(ripple_end)
        ripple_grow.setEasingCurve(QEasingCurve.OutCubic)

        ripple_fade = QPropertyAnimation(ripple_opacity, b"opacity")
        ripple_fade.setDuration(240)
        ripple_fade.setStartValue(0.9)
        ripple_fade.setEndValue(0.0)
        ripple_fade.setEasingCurve(QEasingCurve.OutQuad)

        splash_group = QParallelAnimationGroup(self)
        splash_group.addAnimation(ripple_grow)
        splash_group.addAnimation(ripple_fade)

        splash_offsets = [
            QPoint(-30, -15), QPoint(-21, 18), QPoint(24, -18),
            QPoint(31, 11), QPoint(-5, -30), QPoint(8, 25)
        ]

        splash_widgets = [ripple]
        for i, offset in enumerate(splash_offsets):
            dot, opacity = self.make_splash_dot(plus_center, 6 if i % 2 else 8)
            splash_widgets.append(dot)

            dot_end = QRect(
                plus_center.x() + offset.x(),
                plus_center.y() + offset.y(),
                max(2, dot.width() - 3),
                max(2, dot.height() - 3)
            )

            dot_move = QPropertyAnimation(dot, b"geometry")
            dot_move.setDuration(260)
            dot_move.setStartValue(dot.geometry())
            dot_move.setEndValue(dot_end)
            dot_move.setEasingCurve(QEasingCurve.OutCubic)

            dot_fade = QPropertyAnimation(opacity, b"opacity")
            dot_fade.setDuration(260)
            dot_fade.setStartValue(1.0)
            dot_fade.setEndValue(0.0)
            dot_fade.setEasingCurve(QEasingCurve.OutQuad)

            splash_group.addAnimation(dot_move)
            splash_group.addAnimation(dot_fade)

        # Start materializing the tab while the splash is still fading.
        def start_tab_materialize():
            self.active_llms.append(new_llm)
            self.save_setting("active_llms", json.dumps(self.active_llms))
            self.render_active_llms()
            self.play_plus_to_tab_animation(old_plus_rect, new_llm["id"])

        QTimer.singleShot(75, start_tab_materialize)

        def cleanup_splash():
            for widget in splash_widgets:
                widget.deleteLater()

        splash_group.finished.connect(cleanup_splash)
        self.tab_animations.append(splash_group)
        splash_group.start()

    def play_plus_to_tab_animation(self, old_plus_rect, new_llm_id):
        new_tab = self.llm_buttons.get(new_llm_id)
        if not new_tab:
            self.add_button.setEnabled(True)
            return

        new_tab_rect = self.widget_rect_in_panel(new_tab)
        new_plus_rect = self.widget_rect_in_panel(self.add_button)

        new_tab.hide()
        self.add_button.hide()

        # Temporary tab clone: makes it look like the plus becomes the new LLM tab.
        tab_clone = QPushButton(new_tab.text(), self)
        tab_clone.setGeometry(old_plus_rect)
        tab_clone.show()
        tab_clone.raise_()

        # Temporary plus clone: makes it look like the plus button ploops to the right.
        plus_clone = QPushButton("+", self)
        plus_clone.setObjectName("addButton")
        plus_clone.setFixedSize(self.add_button.size())
        plus_clone.setGeometry(old_plus_rect)
        plus_clone.show()
        plus_clone.raise_()

        tab_anim = QPropertyAnimation(tab_clone, b"geometry")
        tab_anim.setDuration(260)
        tab_anim.setStartValue(old_plus_rect)
        tab_anim.setEndValue(new_tab_rect)
        tab_anim.setEasingCurve(QEasingCurve.OutBack)

        plus_anim = QPropertyAnimation(plus_clone, b"geometry")
        plus_anim.setDuration(320)
        plus_anim.setStartValue(old_plus_rect)
        plus_anim.setEndValue(new_plus_rect)
        plus_anim.setEasingCurve(QEasingCurve.OutBack)

        group = QParallelAnimationGroup(self)
        group.addAnimation(tab_anim)
        group.addAnimation(plus_anim)

        def finish():
            tab_clone.deleteLater()
            plus_clone.deleteLater()
            new_tab.show()
            self.add_button.show()
            self.add_button.setEnabled(True)

        group.finished.connect(finish)
        self.tab_animations.append(group)
        group.start()

    def create_layout(self):
        top_bar = QHBoxLayout()
        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(45)

        top_bar.setContentsMargins(18, 4, 18, 4)
        top_bar.addWidget(self.scroll_area, alignment=Qt.AlignVCenter)
        top_bar.addStretch()
        top_bar.addWidget(self.settings_button, alignment=Qt.AlignVCenter)
        top_bar.addWidget(self.close_button, alignment=Qt.AlignVCenter)

        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(12, 12, 12, 12)

        self.title_bar.setLayout(top_bar)
        container_layout.addWidget(self.title_bar)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.browser)
        self.content_stack.addWidget(self.setting_panel)
        self.content_stack.setCurrentWidget(self.browser)

        container_layout.addWidget(self.content_stack, 1)
        self.container.setLayout(container_layout)

        saved_color = self.settings.value("resize_color", "transparent")
        self.container.setStyleSheet(
            f"QFrame#mainContainer {{ background-color: {saved_color}; border: 1px solid rgba(255, 255, 255, 20); border-radius: 24px; }}")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)
        self.setLayout(main_layout)

    def show_browser(self):
        self.content_stack.setCurrentWidget(self.browser)

    def open_llm_url(self, name, url, llm_id=None):
        self.show_browser()
        self.browser.setUrl(QUrl(url))

    def close_panel(self):
        self.reset_to_browser()
        if self.bubble:
            self.bubble.close_chat_with_animation()
        else:
            self.hide()

    def update_content_area_color(self, new_color):
        self.container.setStyleSheet(
            f"QFrame#mainContainer {{ background-color: {new_color}; border: 1px solid rgba(255, 255, 255, 20); border-radius: 24px; }}")
        self.save_setting("resize_color", new_color)

    # --- NEW: Function to execute Chromium cache clear ---
    def clear_browsing_data(self):
        # Clears all persistent cookies from the session_data folder
        self.profile.cookieStore().deleteAllCookies()
        # Wipes all cached website files/images
        self.profile.clearHttpCache()
        # Instantly reloads the browser view so the user can verify they are logged out
        self.browser.reload()

        # After wiping data, snap back to the browser so the user can see the login screen again
        self.show_browser()
        # Reset the sidebar toggle back to Appearance for the next time settings is opened
        self.setting_panel.appearance_btn.setChecked(True)
        self.setting_panel.content_stack.setCurrentIndex(0)

    def hideEvent(self, event):
        self.save_setting("window_size", self.size())
        super().hideEvent(event)

    def open_settings(self):
        if self.content_stack.currentWidget() is self.setting_panel:
            self.content_stack.setCurrentWidget(self.browser)
        else:
            self.content_stack.setCurrentWidget(self.setting_panel)

    def get_resize_direction(self, pos):
        w = self.width()
        h = self.height()
        margin = 16
        x, y = pos.x(), pos.y()

        left = x < margin
        right = x > (w - margin)
        top = y < margin
        bottom = y > (h - margin)

        if left and top: return Qt.TopLeftSection
        if right and top: return Qt.TopRightSection
        if left and bottom: return Qt.BottomLeftSection
        if right and bottom: return Qt.BottomRightSection
        if left: return Qt.LeftSection
        if right: return Qt.RightSection
        if top: return Qt.TopSection
        if bottom: return Qt.BottomSection
        return None

    def update_cursor_shape(self, pos):
        direction = self.get_resize_direction(pos)
        if direction in (Qt.TopSection, Qt.BottomSection):
            self.setCursor(QCursor(Qt.SizeVerCursor))
        elif direction in (Qt.LeftSection, Qt.RightSection):
            self.setCursor(QCursor(Qt.SizeHorCursor))
        elif direction in (Qt.TopLeftSection, Qt.BottomRightSection):
            self.setCursor(QCursor(Qt.SizeFDiagCursor))
        elif direction in (Qt.TopRightSection, Qt.BottomLeftSection):
            self.setCursor(QCursor(Qt.SizeBDiagCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            position = event.position().toPoint()
            direction = self.get_resize_direction(position)

            if direction:
                self.resize_direction = direction
                self.initial_geometry = self.geometry()
                self.initial_global_pos = event.globalPosition().toPoint()
                self.pending_geometry = None

                self.browser_was_active_before_resize = (
                        self.content_stack.currentWidget() is self.browser
                )
                if self.browser_was_active_before_resize:
                    self.browser.hide()

                self.resize_timer.start()

                event.accept()
            else:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()

        if not event.buttons() & Qt.LeftButton:
            self.update_cursor_shape(position)
            return

        if self.resize_direction:
            delta = event.globalPosition().toPoint() - self.initial_global_pos
            geom = self.initial_geometry

            left, top, width, height = geom.left(), geom.top(), geom.width(), geom.height()
            min_w, min_h = self.minimumWidth(), self.minimumHeight()

            if self.resize_direction in (Qt.RightSection, Qt.BottomRightSection, Qt.TopRightSection):
                width = max(min_w, geom.width() + delta.x())

            if self.resize_direction in (Qt.BottomSection, Qt.BottomRightSection, Qt.BottomLeftSection):
                height = max(min_h, geom.height() + delta.y())

            if self.resize_direction in (Qt.TopSection, Qt.TopLeftSection):
                max_delta_y = geom.height() - min_h
                actual_delta_y = min(delta.y(), max_delta_y)
                top = geom.top() + actual_delta_y
                height = geom.height() - actual_delta_y

            if self.resize_direction in (Qt.LeftSection, Qt.TopLeftSection, Qt.BottomLeftSection):
                max_delta_x = geom.width() - min_w
                actual_delta_x = min(delta.x(), max_delta_x)
                left = geom.left() + actual_delta_x
                width = geom.width() - actual_delta_x

            if self.resize_direction == Qt.TopRightSection:
                max_delta_y = geom.height() - min_h
                actual_delta_y = min(delta.y(), max_delta_y)
                top = geom.top() + actual_delta_y
                height = geom.height() - actual_delta_y

            target_rect = (left, top, width, height)
            if self.geometry().getRect() != target_rect:
                self.pending_geometry = target_rect

            event.accept()

        elif self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def apply_pending_geometry(self):
        if self.pending_geometry is not None:
            left, top, width, height = self.pending_geometry
            self.setGeometry(left, top, width, height)
            self.pending_geometry = None

    def mouseReleaseEvent(self, event):
        self.drag_position = None

        if self.resize_direction:
            self.resize_direction = None
            self.resize_timer.stop()
            self.apply_pending_geometry()

            if getattr(self, "browser_was_active_before_resize", False):
                self.browser.show()

        self.setCursor(QCursor(Qt.ArrowCursor))
        event.accept()

    def reset_to_browser(self):
        self.content_stack.setCurrentWidget(self.browser)