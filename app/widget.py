from PySide6.QtWidgets import QWidget, QPushButton
from PySide6.QtCore import Qt, QPoint

from app.chat_panel import ChatPanel


class FloatingWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.chat_panel = ChatPanel(self)
        self.drag_position = QPoint()
        self.was_dragging = False

        self.setup_window()
        self.create_button()

    def setup_window(self):
        self.setFixedSize(70, 70)
        self.move(1200, 600)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        self.setAttribute(Qt.WA_TranslucentBackground)

    def create_button(self):
        self.button = QPushButton("AI", self)
        self.button.setFixedSize(60, 60)
        self.button.move(5, 5)

        self.button.setStyleSheet("""
            QPushButton {
                background-color: #202123;
                color: white;
                border-radius: 30px;
                font-size: 20px;
                font-weight: bold;
                border: 2px solid #10a37f;
            }
        """)

        self.button.clicked.connect(self.open_chat)


    def open_chat(self):
        # get bubble position
        bubble_x = self.x()
        bubble_y = self.y()

        #put chat panel slightly above bubble
        self.chat_panel.move(bubble_x - 350, bubble_y - 450)

        #show chat panel
        self.chat_panel.show()
        self.chat_panel.raise_()

        #hide bubble while chat is open
        self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.pos()
            self.was_dragging = False

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.was_dragging = True
            self.move(event.globalPosition().toPoint() - self.drag_position)

    def mouseReleaseEvent(self, event):
        if not self.was_dragging:
            self.open_chat()