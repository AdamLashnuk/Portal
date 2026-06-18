from PySide6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFrame)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
import os

class ChatPanel(QWidget):
    def __init__(self, bubble=None):
        super().__init__()
        self.bubble = bubble
        self.drag_position = None
        self.setup_window()
        self.create_widgets()
        self.create_layout()

    def setup_window(self):
        self.setFixedSize(900, 700)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
                color: #ececec;
                font-family: "Segoe UI";
            }

            QFrame#mainContainer {
                background-color: #212121;
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
                font-size: 28px;
            }

            QPushButton#closeButton:hover {
                color: white;
                background-color: #333333;
                border-radius: 8px;
            }
        """)

    def create_widgets(self):
        self.container = QFrame()
        self.container.setObjectName("mainContainer")

        self.title = QLabel("AI Browser")
        self.title.setObjectName("title")

        self.chatgpt_button = QPushButton("ChatGPT")
        self.claude_button = QPushButton("Claude")
        self.gemini_button = QPushButton("Gemini")

        self.chatgpt_button.clicked.connect(self.open_chatgpt)
        self.claude_button.clicked.connect(self.open_claude)
        self.gemini_button.clicked.connect(self.open_gemini)

        self.close_button = QPushButton("×")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(50, 50)
        self.close_button.clicked.connect(self.close_panel)

        # Persistent logins stored in a local folder
        self.browser = QWebEngineView()
        
        self.profile = QWebEngineProfile("llm_profile", self.browser)
        self.profile = QWebEngineProfile("llm_profile", self.browser)
        self.profile.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        storage_path = os.path.join(project_root, "session_data")
        
        self.profile.setPersistentStoragePath(storage_path)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        
        self.page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(self.page)
        
        self.browser.setUrl(QUrl("https://chatgpt.com"))

    def create_layout(self):
        top_bar = QHBoxLayout()
        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(60)

        top_bar.setContentsMargins(18, 14, 18, 8)

        top_bar.addWidget(self.title)
        top_bar.addSpacing(12)
        top_bar.addWidget(self.chatgpt_button)
        top_bar.addWidget(self.claude_button)
        top_bar.addWidget(self.gemini_button)
        top_bar.addStretch()
        top_bar.addWidget(self.close_button)

        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(12, 12, 12, 12)
        self.title_bar.setLayout(top_bar)
        container_layout.addWidget(self.title_bar)
        container_layout.addWidget(self.browser)

        self.container.setLayout(container_layout)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        self.setLayout(main_layout)

    def open_chatgpt(self):
        self.browser.setUrl(QUrl("https://chatgpt.com"))

    def open_claude(self):
        self.browser.setUrl(QUrl("https://claude.ai"))

    def open_gemini(self):
        self.browser.setUrl(QUrl("https://gemini.google.com"))

    def close_panel(self):
        self.hide()

        if self.bubble:
            self.bubble.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )
            event.accept()


    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(
                event.globalPosition().toPoint()
                - self.drag_position
            )
            event.accept()