from PySide6.QtWidgets import (
    QWidget, QTextEdit, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PySide6.QtCore import Qt, QPoint


class ChatPanel(QWidget):
    def __init__(self, bubble=None):
        super().__init__()
        self.bubble = bubble

        # These are for dragging the panel around
        self.drag_position = QPoint()
        self.is_dragging = False

        self.setup_window()
        self.create_widgets()
        self.create_layout()

    def setup_window(self):
        self.setFixedSize(520, 650)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)


        self.setStyleSheet("""
            QWidget {
                background-color: #212121;
                color: #ececec;
                font-family: "Segoe UI";
            }

            QLabel#title {
                font-size: 22px;
                font-weight: 600;
            }

            QLabel#subtitle {
                font-size: 26px;
                font-weight: 600;
                color: #ececec;
            }

            QTextEdit {
                background-color: #212121;
                color: #ececec;
                border: none;
                font-size: 15px;
                padding: 12px;
            }

            QFrame#inputContainer {
                background-color: #303030;
                border: 1px solid #444444;
                border-radius: 24px;
            }

            QLineEdit {
                background-color: transparent;
                border: none;
                color: #ececec;
                font-size: 15px;
                padding: 12px;
            }

            QLineEdit::placeholder {
                color: #9b9b9b;
            }

            QPushButton#sendButton {
                background-color: #ffffff;
                color: #212121;
                border: none;
                border-radius: 17px;
                font-size: 18px;
                font-weight: bold;
            }

            QPushButton#closeButton {
                background-color: transparent;
                color: #b4b4b4;
                border: none;
                font-size: 28px;
            }

            QPushButton#closeButton:hover {
                color: white;
                background-color: #333333;
                border-radius: 8px;
            }
            
            QFrame#mainContainer {
                background-color: #212121;
                border-radius: 24px;
            }
        """)

    def create_widgets(self):
        self.title = QLabel("ChatGPT")
        self.title.setObjectName("title")

        self.container = QFrame()
        self.container.setObjectName("mainContainer")

        self.close_button = QPushButton("×")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(50, 50)
        self.close_button.clicked.connect(self.close_panel)

        self.subtitle = QLabel("What can I help with?")
        self.subtitle.setObjectName("subtitle")
        self.subtitle.setAlignment(Qt.AlignCenter)

        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        self.chat_box.setPlaceholderText("")

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Ask anything")
        self.input_box.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("↑")
        self.send_button.setObjectName("sendButton")
        self.send_button.setFixedSize(34, 34)
        self.send_button.clicked.connect(self.send_message)

        self.input_container = QFrame()
        self.input_container.setObjectName("inputContainer")

    def create_layout(self):
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(18, 14, 18, 0)
        top_bar.addWidget(self.title)
        top_bar.addStretch()
        top_bar.addWidget(self.close_button)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(16, 10, 16, 10)
        input_row.addWidget(self.input_box)
        input_row.addWidget(self.send_button)

        self.input_container.setLayout(input_row)

        container_layout = QVBoxLayout()
        container_layout.addLayout(top_bar)
        container_layout.addStretch()
        container_layout.addWidget(self.subtitle)
        container_layout.addWidget(self.chat_box)
        container_layout.addWidget(self.input_container)
        container_layout.setContentsMargins(16, 16, 16, 16)

        self.container.setLayout(container_layout)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        self.setLayout(main_layout)

    def close_panel(self):
        self.hide()

        if self.bubble:
            self.bubble.show()

    def send_message(self):
        message = self.input_box.text().strip()

        if message == "":
            return

        self.subtitle.hide()

        self.chat_box.append(f"You:\n{message}\n")
        self.chat_box.append("ChatGPT:\nPlaceholder response for now.\n")

        self.input_box.clear()

    # Mouse event handlers for dragging the top bar of the chat panel
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 60:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.is_dragging = True
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.is_dragging:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            event.accept()