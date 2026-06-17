from PySide6.QtWidgets import (
    QWidget,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
)
from PySide6.QtCore import Qt


class ChatPanel(QWidget):
    def __init__(self, bubble=None):
        super().__init__()
        self.bubble = bubble

        self.setup_window()
        self.create_widgets()
        self.create_layout()

    def setup_window(self):
        self.setFixedSize(400, 550)
        self.move(950, 200)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        self.setStyleSheet("""
            QWidget {
                background-color: #111214;
                color: white;
                font-family: Arial;
            }
        """)

    def create_widgets(self):
        self.title = QLabel("LLM Widget")

        self.close_button = QPushButton("X")
        self.close_button.clicked.connect(self.close_panel)

        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        self.chat_box.append("AI: Hey, ask me anything.")

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type your message...")
        self.input_box.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)

    def close_panel(self):
        self.hide()

        if self.bubble:
            self.bubble.show()

    def create_layout(self):
        top_bar = QHBoxLayout()
        top_bar.addWidget(self.title)
        top_bar.addStretch()
        top_bar.addWidget(self.close_button)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input_box)
        input_row.addWidget(self.send_button)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_bar)
        main_layout.addWidget(self.chat_box)
        main_layout.addLayout(input_row)

        self.setLayout(main_layout)

    def send_message(self):
        message = self.input_box.text().strip()

        if message == "":
            return

        self.chat_box.append(f"\nYou: {message}")
        self.chat_box.append("\nAI: Fake response for now.")

        self.input_box.clear()

