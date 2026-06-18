from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QPen

from app.chat_panel import ChatPanel


class FloatingWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.chat_panel = ChatPanel(self)
        self.drag_position = QPoint()
        self.was_dragging = False

        self.setup_window()

    def setup_window(self):
        # Set a clean size for our circular widget
        self.setFixedSize(60, 60)
        self.move(1200, 600)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        self.setAttribute(Qt.WA_TranslucentBackground)

    # --- DRAW THE CIRCLE DIRECTLY ON THE WIDGET ---
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw the background circle (Matches #202123)
        painter.setBrush(QColor("#202123"))
        # Draw the border (Matches 2px #10a37f)
        painter.setPen(QPen(QColor("#10a37f"), 2))
        painter.drawEllipse(2, 2, 56, 56)

        # Draw the "AI" text
        painter.setPen(QColor("white"))
        font = QFont("Arial", 15, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, "AI")

    def open_chat(self):
        bubble_x = self.x()
        bubble_y = self.y()

        # Initial target coordinates
        target_x = bubble_x - 350
        target_y = bubble_y - 450 

        # Get the dimensions of the monitor the widget is currently on
        screen = self.screen().availableGeometry()
        panel_w = self.chat_panel.width()
        panel_h = self.chat_panel.height()
        
        # Prevent it from clipping past the edges of the screen and make the chat panel open flushly against the edges of the screen
        if target_y < screen.top():
            target_y = screen.top()
            
        if target_y + panel_h > screen.bottom():
            target_y = screen.bottom() - panel_h

        if target_x < screen.left():
            target_x = screen.left()

        if target_x + panel_w > screen.right():
            target_x = screen.right() - panel_w

        # Move and display the panel safely
        self.chat_panel.move(target_x, target_y)
        self.chat_panel.show()
        self.chat_panel.raise_()
        self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.was_dragging = False
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.was_dragging = True
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.was_dragging:
                self.open_chat()
            event.accept()