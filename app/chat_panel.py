from PySide6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QRubberBand)
from PySide6.QtCore import Qt, QUrl, QSize, QTimer, QSettings
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QCursor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtCore import QPropertyAnimation, QEasingCurve
import os
from app.setting_panel import SettingPanel
from PySide6.QtWidgets import QSizePolicy

class ChatPanel(QWidget):
    def __init__(self, bubble=None):
        super().__init__()

        self.bubble = bubble
        self.drag_position = None

        self.resize_margin = 8       # Detects mouse when it is within 8 pixels of an edge
        self.resize_direction = None  # Tracks which edge or corner is being pulled

        # --- Resize throttling ---
        # Raw mouse-move events can fire far faster than the browser can
        # re-layout/re-paint. Instead of resizing the window on every single
        # event, we just store the latest target geometry and let a timer
        # apply it at a steady ~200fps. This keeps the drag feeling live
        # while coalescing bursts of mouse events into one resize per frame.
        self.pending_geometry = None
        self.resize_timer = QTimer(self)
        self.resize_timer.setInterval(5)  # ~200 fps 16 is ~60 fps
        self.resize_timer.timeout.connect(self.apply_pending_geometry)

        self.setup_window()
        self.create_widgets()

        self.setting_panel = SettingPanel()
        self.setting_panel.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )
        self.setting_panel.hide()

        self.create_layout()

    def setup_window(self):
        self.setMinimumSize(400, 400) # Prevents the window from crashing if made too small

        # Initialize QSettings and load the saved size
        self.settings = QSettings("MyLLMWidget", "ChatPanel")
        self.current_provider = self.settings.value("current_provider", "chatgpt")
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
            
            QFrame#contentArea {
                background-color: transparent; /* Solid color hides the Chromium lag tear */
                border-radius: 12px;
            }
        """)

    def create_widgets(self):
        self.container = QFrame()
        self.container.setObjectName("mainContainer")

        self.container.setMouseTracking(True) # Keeps border tracking active over the background

        self.chatgpt_button = QPushButton("ChatGPT")
        self.claude_button = QPushButton("Claude")
        self.gemini_button = QPushButton("Gemini")

        self.chatgpt_button.clicked.connect(self.open_chatgpt)
        self.claude_button.clicked.connect(self.open_claude)
        self.gemini_button.clicked.connect(self.open_gemini)

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(32, 32)
        self.close_button.clicked.connect(self.close_panel)


        # Add button
        self.add_button = QPushButton("+")
        self.add_button.setObjectName("addButton")
        self.add_button.setFixedSize(26, 26)

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

        self.profile = QWebEngineProfile("llm_profile", self.browser)

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        storage_path = os.path.join(project_root, "session_data")
        
        self.profile.setPersistentStoragePath(storage_path)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        
        self.page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(self.page)

        if self.current_provider == "chatgpt":
            self.browser.setUrl(QUrl("https://chatgpt.com"))
        elif self.current_provider == "claude":
            self.browser.setUrl(QUrl("https://claude.ai"))
        elif self.current_provider == "gemini":
            self.browser.setUrl(QUrl("https://gemini.google.com"))
        else:
            self.browser.setUrl(QUrl("https://chatgpt.com"))

    def create_layout(self):
        top_bar = QHBoxLayout()
        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(45)

        top_bar.setContentsMargins(18, 4, 18, 4)
        
        top_bar.setAlignment(Qt.AlignVCenter)

        top_bar.addWidget(self.chatgpt_button)
        top_bar.addWidget(self.claude_button)
        top_bar.addWidget(self.gemini_button)
        top_bar.addWidget(self.add_button)


        top_bar.addStretch()
        top_bar.addWidget(self.settings_button)
        top_bar.addWidget(self.close_button, alignment=Qt.AlignVCenter)

        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(12, 12, 12, 12)
        self.title_bar.setLayout(top_bar)
        container_layout.addWidget(self.title_bar)

        self.content_area = QFrame()
        self.content_area.setObjectName("contentArea")

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)

        content_layout.addWidget(self.browser)
        content_layout.addWidget(self.setting_panel)

        self.content_area.setLayout(content_layout)

        container_layout.addWidget(self.content_area)

        self.setting_panel.hide()

        self.container.setLayout(container_layout)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        self.setLayout(main_layout)

    def show_browser(self):
        self.setting_panel.hide()
        self.browser.show()

    def open_chatgpt(self):
        self.current_provider = "chatgpt"
        self.settings.setValue("current_provider", self.current_provider)
        self.show_browser()
        self.browser.setUrl(QUrl("https://chatgpt.com"))

    def open_claude(self):
        self.current_provider = "claude"
        self.settings.setValue("current_provider", self.current_provider)
        self.show_browser()
        self.browser.setUrl(QUrl("https://claude.ai"))

    def open_gemini(self):
        self.current_provider = "gemini"
        self.settings.setValue("current_provider", self.current_provider)
        self.show_browser()
        self.browser.setUrl(QUrl("https://gemini.google.com"))

    def close_panel(self):
        if self.bubble:
            self.bubble.close_chat_with_animation()
        else:
            self.hide()

    def hideEvent(self, event):
            # Automatically save the current size to QSettings whenever the panel disappear. The reason why im not putting this in close_panel is because close_panel only works if the user presses on the x button, hideEvent works on any type of close.
            self.settings.setValue("window_size", self.size())
            super().hideEvent(event)

    def open_settings(self):
            if self.setting_panel.isVisible():
                self.setting_panel.hide()
                self.browser.show()
            else:
                self.browser.hide()
                self.setting_panel.show()
    
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
                # instead we swap it out for the solid content_area background
                # for the duration of the drag, and only show it again once
                # the resize is finished and the timer has stopped.
                # if you want the browser to be visible during resizing, change .hide() to .show().
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
            # every frame of the drag.
            self.browser.show()

        self.setCursor(QCursor(Qt.ArrowCursor))
        event.accept()