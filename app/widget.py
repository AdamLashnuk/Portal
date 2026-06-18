from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from PySide6.QtCore import Qt, QPoint, QRect
from app.animation_window import AnimationWindow

from app.chat_panel import ChatPanel


class FloatingWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.chat_panel = ChatPanel(self)
        self.drag_position = QPoint()
        self.was_dragging = False
        self.animation_window = AnimationWindow()
        self.animation_window.finished.connect(self.show_chat_panel_after_animation)

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

    def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw the background circle (Matches #202123)
            painter.setBrush(QColor("#202123"))
            painter.setPen(Qt.NoPen)  # This removes the green outline
            painter.drawEllipse(2, 2, 56, 56)

            logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "logo.png")
            logo = QPixmap(logo_path)

            # 3. Create a circular path
            circular_path = QPainterPath()
            circular_path.addEllipse(QRect(2, 2, 56, 56))

            # 4. Enable clipping to the circle
            painter.setClipPath(circular_path)

            # 5. Draw the logo (now it will be clipped to circle)
            if not logo.isNull():
                scaled_logo = logo.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                painter.drawPixmap(2, 2, scaled_logo)


    def open_chat(self):
        bubble_x = self.x()
        bubble_y = self.y()

        target_x = bubble_x - 350
        target_y = bubble_y - 450

        if target_y < 10:
            target_y = bubble_y + self.height() + 10

        if target_x < 10:
            target_x = 10

        self.final_chat_x = target_x
        self.final_chat_y = target_y

        start_rect = QRect(
            self.x(),
            self.y(),
            self.width(),
            self.height()
        )

        end_rect = QRect(
            target_x,
            target_y,
            self.chat_panel.width(),
            self.chat_panel.height()
        )

        self.hide()
        self.animation_window.grow_from_to(start_rect, end_rect)

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

    def show_chat_panel_after_animation(self):
        self.chat_panel.move(self.final_chat_x, self.final_chat_y)
        self.chat_panel.show()
        self.chat_panel.raise_()