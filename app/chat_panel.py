import os
import json
import uuid
from PySide6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
                               QFrame, QRubberBand, QGraphicsOpacityEffect, QSizePolicy,
                               QScrollArea, QDialog, QLineEdit, QListWidget, QListWidgetItem,
                               QStackedWidget, QMenu, QInputDialog)
from PySide6.QtCore import Qt, QUrl, QSize, QTimer, QSettings, QPropertyAnimation, QEasingCurve, Signal, QPoint
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QCursor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

from app.setting_panel import SettingPanel


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

        self.resize_margin = 8       # Detects mouse when it is within 8 pixels of an edge
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
        # No explicit hide() here — once create_layout() adds this to
        # self.content_stack, the stack itself controls which of
        # browser/setting_panel is visible via setCurrentWidget().

        # Listen for the signal from the settings panel
        self.setting_panel.color_changed.connect(self.update_content_area_color)

        # 2. THIS MUST COME LAST: It puts the widgets into the layout
        self.create_layout()

    def save_setting(self, key, value):
        # QSettings normally only guarantees a write hits disk when the
        # object is cleanly destroyed or sync() is called explicitly — Qt
        # does NOT promise an immediate flush on setValue() alone. This app
        # has no quit handler (closing the chat panel just hides it; the
        # bubble keeps the process alive), so the only way these settings
        # are likely to ever get a clean shutdown is if the OS itself
        # terminates the process — and that can happen before the normal
        # flush gets a chance to run. Calling sync() right after every
        # write makes sure "Set as Default" (and everything else) actually
        # survives the app being closed abruptly, not just a clean exit.
        self.settings.setValue(key, value)
        self.settings.sync()

    def setup_window(self):
        self.setMinimumSize(400, 400) # Prevents the window from crashing if made too small
        
        # Initialize QSettings and load the saved size
        self.settings = QSettings("MyLLMWidget", "ChatPanel")
        self.current_provider = self.settings.value("current_provider", "ChatGPT")
        # current_provider_id is the preferred way to identify the default
        # LLM (added alongside Rename/Delete/Duplicate/Set as Default) since
        # current_provider alone (a name) can't disambiguate two entries
        # with the same name, e.g. after using Duplicate. Falls back to
        # name-matching below if no id was ever saved (older settings).
        self.current_provider_id = self.settings.value("current_provider_id", None)
        
        # --- FIX: Load the custom LLM array explicitly BEFORE rendering widgets ---
        active_str = self.settings.value("active_llms")
        if active_str:
            self.active_llms = json.loads(active_str)
            # Migration: entries saved before the "id" field existed (added
            # for rename/delete/duplicate/set-default support) won't have
            # one yet. Backfill so every entry has a stable identity that
            # doesn't break if two entries end up sharing a name (e.g. via
            # Duplicate).
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
            self.resize(900, 700) # Default fallback size

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setMouseTracking(True)   # Allows the program to watch the mouse move across borders

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
        self.container.setMouseTracking(True) # Keeps border tracking active over the background

        # --- HORIZONTAL SCROLL AREA FOR DYNAMIC BUTTONS ---
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

        # Add button — created here (before render_active_llms() runs)
        # because render_active_llms() places it inside self.llm_layout,
        # right after the last LLM button, so it scrolls along with them
        # and always appears immediately after whichever LLM was added last.
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

        # Settings button
        self.settings_button = QPushButton()
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setFixedSize(32, 32)
        self.settings_button.clicked.connect(self.open_settings)

        # Load and recolor the gear icon
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(project_root, "assets", "gearsettings.png")
        
        icon_pixmap = QPixmap(icon_path)
        if not icon_pixmap.isNull():
            painter = QPainter(icon_pixmap)
            # This line allows us to draw over the non-transparent parts of the PNG
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn) 
            painter.fillRect(icon_pixmap.rect(), QColor("#b4b4b4"))
            painter.end()
            
            self.settings_button.setIcon(QIcon(icon_pixmap))
            self.settings_button.setIconSize(QSize(20, 20))

        # Persistent logins stored in a local folder
        self.browser = QWebEngineView()

        # QWebEngineView's sizeHint() can report a small default before its
        # render widget finishes initializing/loading the first page, which
        # can throw off QVBoxLayout's space distribution. Forcing
        # Expanding/Expanding here makes the layout always give it 100% of
        # leftover space, regardless of what its sizeHint reports.
        #
        # retainSizeWhenHidden=True is the critical part: during a resize
        # drag, self.browser.hide() is called (see mousePressEvent) to avoid
        # forcing Chromium to re-layout on every frame. By default, Qt
        # removes a hidden widget from layout space calculations entirely —
        # so the moment the browser hid, container_layout only had the
        # fixed-height title_bar left to lay out inside the whole window,
        # and centered it in the leftover space (the title bar "dropping to
        # the middle" bug). Retaining its size means the layout keeps
        # reserving the same space for it whether it's visible or not, so
        # title_bar stays pinned to the top throughout the entire drag.
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

        # Set default URL based on saved provider.
        # Prefer matching by id (set via "Set as Default" in the right-click
        # menu) since it's stable even across duplicate names; fall back to
        # name-matching for settings saved before ids existed.
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
        # Clear everything from the layout before rebuilding — both widgets
        # and non-widget items like the trailing stretch. takeAt() removes
        # the item from the layout regardless of its type; only widgets
        # need setParent(None) afterward so they're not deleted (add_button
        # is reused, not recreated, on every call).
        while self.llm_layout.count():
            item = self.llm_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        # Build buttons from the array memory
        for llm in self.active_llms:
            btn = QPushButton(llm["name"])
            # Lambda uses default arguments to securely capture the variable at render time
            btn.clicked.connect(
                lambda checked=False, name=llm["name"], url=llm["url"], llm_id=llm["id"]:
                    self.open_llm_url(name, url, llm_id)
            )

            # Right-click opens a context menu with Rename / Duplicate /
            # Set as Default / Delete for this specific entry. Left-click
            # is already taken (opens the LLM), so right-click is the
            # natural place for "more options on this item" — same pattern
            # as browser tabs and file managers.
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, button=btn, llm_id=llm["id"]:
                    self.show_llm_context_menu(button, llm_id)
            )

            self.llm_layout.addWidget(btn, alignment=Qt.AlignVCenter)

        # The "+" button always goes right after the last LLM button.
        self.llm_layout.addWidget(self.add_button, alignment=Qt.AlignVCenter)

        # Soaks up any leftover space inside llm_container so the buttons
        # stay packed on the left instead of being centered when the
        # scroll area's viewport is wider than the buttons need.
        self.llm_layout.addStretch()

    def show_llm_context_menu(self, button, llm_id):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1f1f1f;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 4px;
                color: #ececec;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #333333;
            }
            QMenu::separator {
                height: 1px;
                background: #333333;
                margin: 4px 8px;
            }
        """)

        rename_action = menu.addAction("Rename")
        duplicate_action = menu.addAction("Duplicate")
        default_action = menu.addAction("Set as Default")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        # Disable "Set as Default" if this entry already is the default —
        # nothing to do, and it's clearer feedback than letting it silently
        # no-op.
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
            if llm["id"] == llm_id:
                return i
        return -1

    def rename_llm_entry(self, llm_id):
        index = self._find_llm_index(llm_id)
        if index == -1:
            return

        old_name = self.active_llms[index]["name"]
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        new_name = new_name.strip()

        if not ok or not new_name or new_name == old_name:
            return

        self.active_llms[index]["name"] = new_name

        # If this entry happens to be the saved default, keep the display
        # name in sync (current_provider is matched on name as a fallback
        # for settings saved before current_provider_id existed).
        if llm_id == self.current_provider_id:
            self.current_provider = new_name
            self.save_setting("current_provider", self.current_provider)

        self.save_setting("active_llms", json.dumps(self.active_llms))
        self.render_active_llms()

    def duplicate_llm_entry(self, llm_id):
        index = self._find_llm_index(llm_id)
        if index == -1:
            return

        original = self.active_llms[index]
        copy_entry = {
            "id": str(uuid.uuid4()),
            "name": original["name"],
            "url": original["url"],
        }
        # Insert right after the original, not just appended at the end,
        # so the duplicate is easy to find.
        self.active_llms.insert(index + 1, copy_entry)

        self.save_setting("active_llms", json.dumps(self.active_llms))
        self.render_active_llms()

    def set_default_llm_entry(self, llm_id):
        index = self._find_llm_index(llm_id)
        if index == -1:
            return

        entry = self.active_llms[index]
        self.current_provider = entry["name"]
        self.current_provider_id = entry["id"]
        self.save_setting("current_provider", self.current_provider)
        self.save_setting("current_provider_id", self.current_provider_id)

        # Re-render so the "Set as Default ✓" disabled state in the context
        # menu reflects the new default immediately on next right-click.
        self.render_active_llms()

    def delete_llm_entry(self, llm_id):
        index = self._find_llm_index(llm_id)
        if index == -1:
            return

        entry = self.active_llms[index]
        del self.active_llms[index]

        # If we just deleted the default entry, fall back to the first
        # remaining LLM (if any) rather than leaving a dangling reference
        # to an id that no longer exists.
        if llm_id == self.current_provider_id:
            if self.active_llms:
                fallback = self.active_llms[0]
                self.current_provider = fallback["name"]
                self.current_provider_id = fallback["id"]
            else:
                self.current_provider = "ChatGPT"
                self.current_provider_id = None
            self.save_setting("current_provider", self.current_provider)
            self.save_setting("current_provider_id", self.current_provider_id)

        self.save_setting("active_llms", json.dumps(self.active_llms))
        self.render_active_llms()

        # If the LLM being viewed right now was the one just deleted, swap
        # the browser over to whatever the (possibly new) default is, so
        # the panel isn't left showing a page for an entry that no longer
        # exists in the bar.
        if entry["name"] == self.current_provider and self.active_llms:
            self.browser.setUrl(QUrl(self.active_llms[0]["url"]))

    def open_add_llm_menu(self):
        dialog = AddLLMDialog(self)
        dialog.llm_selected.connect(self.add_llm_to_bar)
        
        # Position popup directly under the + button
        button_pos = self.add_button.mapToGlobal(QPoint(0, self.add_button.height()))
        dialog.move(button_pos.x() - (dialog.width() // 2), button_pos.y() + 5)
        dialog.exec()

    def add_llm_to_bar(self, name, url):
        # Prevent duplicates
        if any(llm["name"] == name for llm in self.active_llms):
            return
        
        self.active_llms.append({"id": str(uuid.uuid4()), "name": name, "url": url})
        self.save_setting("active_llms", json.dumps(self.active_llms))
        self.render_active_llms()

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

        # The browser and settings panel need to occupy the exact same
        # region (covering the whole panel below the title bar), with only
        # one visible at a time — not stacked one above the other as
        # vertical siblings, which was squashing the settings panel into
        # whatever leftover space was left below the (always space-
        # reserving) browser. A QStackedWidget shows exactly one child at a
        # time, each given the stack's full size, which is exactly this.
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.browser)
        self.content_stack.addWidget(self.setting_panel)
        self.content_stack.setCurrentWidget(self.browser)

        container_layout.addWidget(self.content_stack, 1)

        self.container.setLayout(container_layout)

        # Apply initial layout background color directly to mainContainer shell
        saved_color = self.settings.value("resize_color", "transparent")
        self.container.setStyleSheet(f"QFrame#mainContainer {{ background-color: {saved_color}; border: 1px solid rgba(255, 255, 255, 20); border-radius: 24px; }}")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        self.setLayout(main_layout)

    def show_browser(self):
        self.content_stack.setCurrentWidget(self.browser)

    def open_llm_url(self, name, url, llm_id=None):
        # Clicking an LLM just loads it into the browser for this session —
        # it no longer touches current_provider/current_provider_id. Those
        # are only changed by the explicit "Set as Default" action in the
        # right-click menu now, so opening ChatGPT to check something
        # doesn't silently change what launches next time the app starts.
        self.show_browser()
        self.browser.setUrl(QUrl(url))

    def close_panel(self):
        self.reset_to_browser()
        if self.bubble:
            self.bubble.close_chat_with_animation()
        else:
            self.hide()

    def update_content_area_color(self, new_color):
        self.container.setStyleSheet(f"QFrame#mainContainer {{ background-color: {new_color}; border: 1px solid rgba(255, 255, 255, 20); border-radius: 24px; }}")
        self.save_setting("resize_color", new_color)

    def hideEvent(self, event):
        # Automatically save the current size to QSettings whenever the panel disappears.
        self.save_setting("window_size", self.size())
        super().hideEvent(event)

    def open_settings(self):
        if self.content_stack.currentWidget() is self.setting_panel:
            self.content_stack.setCurrentWidget(self.browser)
        else:
            self.content_stack.setCurrentWidget(self.setting_panel)
    
    # Resize logic
    def get_resize_direction(self, pos):
        w = self.width()
        h = self.height()
        margin = 16 # Large margin to easily catch the 24px rounded corners
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

                # The browser is a separate Chromium process — hiding/disabling
                # it doesn't stop it from re-rendering on every resize. So
                # instead we swap it out for the solid background
                # for the duration of the drag, and only show it again once
                # the resize is finished and the timer has stopped.
                #
                # Only do this if the browser is actually the active page —
                # if settings are open, the browser is already hidden by
                # content_stack and should stay that way; forcing it to
                # show() again on release was the cause of the browser
                # appearing to "stack on top of" settings after a resize.
                self.browser_was_active_before_resize = (
                    self.content_stack.currentWidget() is self.browser
                )
                if self.browser_was_active_before_resize:
                    self.browser.hide()

                self.resize_timer.start()

                event.accept()
            else:
                # Dynamic dragging
                # Any click that wasn't on a corner (resize), a button, or the browser 
                # will fall to here. This dynamically makes the entire top bar 
                # draggable without any hardcoded numbers.
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        
        if not event.buttons() & Qt.LeftButton:
            self.update_cursor_shape(position)
            return

        if self.resize_direction:
            # Calculate exactly how many pixels the mouse has traveled since clicking
            delta = event.globalPosition().toPoint() - self.initial_global_pos
            geom = self.initial_geometry
            
            # Start with current dimensions as base
            left, top, width, height = geom.left(), geom.top(), geom.width(), geom.height()
            min_w, min_h = self.minimumWidth(), self.minimumHeight()

            # --- PRECISE DIRECTION MATH ---
            # Right Edge / Bottom Right / Top Right
            if self.resize_direction in (Qt.RightSection, Qt.BottomRightSection, Qt.TopRightSection):
                width = max(min_w, geom.width() + delta.x())
                
            # Bottom Edge / Bottom Right / Bottom Left
            if self.resize_direction in (Qt.BottomSection, Qt.BottomRightSection, Qt.BottomLeftSection):
                height = max(min_h, geom.height() + delta.y())

            # Top Edge / Top Left
            if self.resize_direction in (Qt.TopSection, Qt.TopLeftSection):
                max_delta_y = geom.height() - min_h
                actual_delta_y = min(delta.y(), max_delta_y)
                top = geom.top() + actual_delta_y
                height = geom.height() - actual_delta_y

            # Left Edge / Top Left / Bottom Left
            if self.resize_direction in (Qt.LeftSection, Qt.TopLeftSection, Qt.BottomLeftSection):
                max_delta_x = geom.width() - min_w
                actual_delta_x = min(delta.x(), max_delta_x)
                left = geom.left() + actual_delta_x
                width = geom.width() - actual_delta_x

            # Special Case: Top Right Corner (Changes height/top, but anchors 'left' completely)
            if self.resize_direction == Qt.TopRightSection:
                max_delta_y = geom.height() - min_h
                actual_delta_y = min(delta.y(), max_delta_y)
                top = geom.top() + actual_delta_y
                height = geom.height() - actual_delta_y

            # Don't resize the window directly here — just record the target
            # geometry. The resize_timer picks this up at a steady ~60fps,
            # so a burst of mouse events between frames only results in one
            # resize instead of many.
            target_rect = (left, top, width, height)
            if self.geometry().getRect() != target_rect:
                self.pending_geometry = target_rect

            event.accept()
            
        elif self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def apply_pending_geometry(self):
        # Called by resize_timer at ~60fps while a resize drag is active.
        # Only touches the window geometry — the browser stays hidden and
        # untouched until the drag finishes, so this stays cheap.
        if self.pending_geometry is not None:
            left, top, width, height = self.pending_geometry
            self.setGeometry(left, top, width, height)
            self.pending_geometry = None

    def mouseReleaseEvent(self, event):
        self.drag_position = None

        if self.resize_direction:
            self.resize_direction = None

            # Stop throttling and make sure the final geometry is applied
            # (in case the last move landed between timer ticks).
            self.resize_timer.stop()
            self.apply_pending_geometry()

            # Resume the browser now that resizing is done, so it only
            # has to re-layout once at the final size instead of on
            # every frame of the drag — but only if it was actually the
            # active page when the drag started (see mousePressEvent).
            if getattr(self, "browser_was_active_before_resize", False):
                self.browser.show()

        self.setCursor(QCursor(Qt.ArrowCursor))
        event.accept()

    def reset_to_browser(self):
        self.content_stack.setCurrentWidget(self.browser)