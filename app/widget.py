import os
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QColor, QPixmap, QPainterPath
from PySide6.QtCore import Qt, QPoint, QRect
from app.animation_window import AnimationWindow
from PySide6.QtGui import QPen
from app.chat_panel import ChatPanel


class FloatingWidget(QWidget):
    def __init__(self):
        super().__init__()


        self.is_hovered = False
        self.chat_panel = ChatPanel(self)
        self.drag_position = QPoint()
        self.was_dragging = False
        self.animation_window = AnimationWindow()
        self.animation_window.open_finished.connect(self.show_chat_panel_after_animation)
        self.animation_window.close_finished.connect(self.show_bubble_after_animation)

        self.setup_window()

    def setup_window(self):
        # Set a clean size for our circular widget
        self.setFixedSize(90, 90)
        self.move(1200, 600)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_Hover)
        self.setAttribute(Qt.WA_TranslucentBackground)

    # Draw the circle directly on the widget
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.is_hovered:
            painter.setBrush(QColor(15, 15, 15, 170))
            painter.setPen(QPen(QColor(255, 255, 255, 30), 1))

            painter.drawRoundedRect(
                2,
                2,
                self.width() - 4,
                self.height() - 4,
                20,
                20
            )

        logo_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets",
            "portal.png"
        )

        logo = QPixmap(logo_path)

        if logo.isNull():
            return

        scaled_logo = logo.scaled(
            85,
            85,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        x = (self.width() - scaled_logo.width()) // 2
        y = (self.height() - scaled_logo.height()) // 2

        painter.drawPixmap(x, y, scaled_logo)

    def open_chat(self):
        bubble_x = self.x()
        bubble_y = self.y()

        screen = self.screen().availableGeometry()
        panel_w = self.chat_panel.width()
        panel_h = self.chat_panel.height()

        target_x = bubble_x - 350
        target_y = bubble_y - 450

        # Prevent it from clipping past the edges of the screen and make the chat panel open flushly against the edges of the screen
        if target_y < screen.top():
            target_y = screen.top()

        if target_y + panel_h > screen.bottom():
            target_y = screen.bottom() - panel_h

        if target_x < screen.left():
            target_x = screen.left()

        if target_x + panel_w > screen.right():
            target_x = screen.right() - panel_w
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
        self.chat_panel.reset_to_browser()
        self.chat_panel.show()
        self.chat_panel.raise_()


    def enterEvent(self, event):
        self.is_hovered = True
        self.update()

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()

    def close_chat_with_animation(self):
        start_rect = QRect(
            self.chat_panel.x(),
            self.chat_panel.y(),
            self.chat_panel.width(),
            self.chat_panel.height()
        )

        end_rect = QRect(
            self.x(),
            self.y(),
            self.width(),
            self.height()
        )
        self.chat_panel.browser.hide()
        self.chat_panel.hide()
        self.animation_window.shrink_from_to(start_rect, end_rect)

    def show_bubble_after_animation(self):
        self.show()
        self.raise_()