import os
from PySide6.QtWidgets import QWidget, QSystemTrayIcon, QMenu, QApplication
from PySide6.QtCore import Qt, QPoint, QRect, QSettings
from PySide6.QtGui import QPainter, QColor, QPixmap, QPainterPath, QPen, QAction, QIcon, QCursor
from app.animation_window import AnimationWindow
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
        self.chat_panel.setting_panel.widget_position_changed.connect(self.set_widget_position_mode)
        self.setup_tray_icon()

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

        self.settings = QSettings("MyLLMWidget", "ChatPanel")
        self.widget_position_mode = self.settings.value("widget_position_mode", "free")
        self.apply_widget_position_mode()

    def set_widget_position_mode(self, mode):
        self.widget_position_mode = mode
        self.settings.setValue("widget_position_mode", mode)
        self.settings.sync()
        self.apply_widget_position_mode()

    def apply_widget_position_mode(self):
        if getattr(self, "widget_position_mode", "free") == "free":
            return
        self.move(self.corner_position_for_mode(self.widget_position_mode))

        if self.chat_panel.isVisible():
            panel_x, panel_y = self.calculate_chat_position()
            self.chat_panel.move(panel_x, panel_y)

    def target_screen_geometry(self):
        """
        Return the screen the widget/panel is currently on.

        This matters on multi-monitor setups because QApplication.primaryScreen()
        always returns the primary monitor, even if the bubble is sitting on a
        secondary monitor. Corner locking should use the monitor the user is
        actually working on.
        """
        if self.chat_panel.isVisible():
            point = self.chat_panel.frameGeometry().center()
        else:
            point = self.frameGeometry().center()

        screen = QApplication.screenAt(point)
        if screen is None:
            screen = QApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QApplication.primaryScreen()

        return screen.availableGeometry()

    def corner_position_for_mode(self, mode):
        margin = 24
        screen = self.target_screen_geometry()

        # Use left + width instead of QRect.right(). QRect.right() is inclusive,
        # which can be off by one and gets confusing with negative monitor coords.
        left = screen.left()
        top = screen.top()
        right_x = screen.left() + screen.width() - self.width()
        bottom_y = screen.top() + screen.height() - self.height()

        if mode == "top_left":
            return QPoint(left + margin, top + margin)
        if mode == "top_right":
            return QPoint(right_x - margin, top + margin)
        if mode == "bottom_left":
            return QPoint(left + margin, bottom_y - margin)
        if mode == "bottom_right":
            return QPoint(right_x - margin, bottom_y - margin)

        return self.pos()

    def setup_tray_icon(self):
        logo_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets",
            "portalbig.png"
        )

        # Initialize the tray icon
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(logo_path))

        # Create the right-click menu
        self.tray_menu = QMenu()

        # Style the menu to match the dark theme
        self.tray_menu.setStyleSheet("""
            QMenu {
                background-color: #1f1f1f;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 4px;
                color: #ececec;
                font-family: "Segoe UI";
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

        # 1. Show/Hide Action
        self.toggle_action = QAction("Show / Hide Widget", self)
        self.toggle_action.triggered.connect(self.toggle_widget)
        self.tray_menu.addAction(self.toggle_action)

        # 2. Settings Action
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings_directly)
        self.tray_menu.addAction(settings_action)

        # 3. Reset Window Position — safeguard against the bubble/chat
        # panel getting stranded off-screen (e.g. dragged onto a second
        # monitor that later gets unplugged). Snaps both back to the
        # primary screen regardless of where they currently are.
        reset_position_action = QAction("Reset Window Position", self)
        reset_position_action.triggered.connect(self.reset_window_position)
        self.tray_menu.addAction(reset_position_action)

        self.tray_menu.addSeparator()

        # 4. Quit Action
        quit_action = QAction("Quit LLM Widget", self)
        quit_action.triggered.connect(self.quit_app)
        self.tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        # Allow left-clicking the tray icon to show/hide
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def toggle_widget(self):
        # If anything is on screen, hide it completely
        if self.chat_panel.isVisible() or self.isVisible():
            self.chat_panel.hide()
            self.hide()
        else:
            # If everything is hidden, bring the bubble back
            self.show()
            self.raise_()

    def reset_window_position(self):
        """
        Safeguard against the bubble/chat panel getting stranded off-screen
        — e.g. the user drags the bubble onto a second monitor, closes the
        app, later unplugs that monitor, and reopens the app to find
        everything spawned somewhere they can no longer click. This forces
        both windows back onto the primary screen's center, regardless of
        which one is currently visible, and leaves the app in the same
        open/closed state it was already in (just relocated) rather than
        triggering the open/close animation.
        """
        screen = self.target_screen_geometry()

        # Center the bubble on the current screen, unless the user locked it to a corner.
        if self.widget_position_mode == "free":
            bubble_x = screen.center().x() - (self.width() // 2)
            bubble_y = screen.center().y() - (self.height() // 2)
            self.move(bubble_x, bubble_y)
        else:
            self.apply_widget_position_mode()

        # Recompute the chat panel's usual offset-from-bubble position,
        # now anchored to the bubble's new (on-screen) location, instead
        # of wherever the panel currently is.
        panel_x, panel_y = self.calculate_chat_position()

        # calculate_chat_position() clamps against the screen edges, but
        # on an unusually small primary monitor (narrower/shorter than the
        # chat panel itself) its sequential left-then-right clamping can
        # still leave the panel's top-left corner off-screen. Since the
        # whole point of this feature is guaranteeing the panel ends up
        # somewhere clickable, clamp once more here directly so the panel
        # is never positioned with a negative/off-screen origin, even on a
        # tiny screen.
        panel_x = max(screen.left(), min(panel_x, screen.left() + screen.width() - self.chat_panel.width()))
        panel_y = max(screen.top(), min(panel_y, screen.top() + screen.height() - self.chat_panel.height()))

        self.chat_panel.move(panel_x, panel_y)

        # Whichever was visible stays visible — this only relocates them,
        # it doesn't change open/closed state or trigger any animation.
        if self.chat_panel.isVisible():
            self.chat_panel.raise_()
        if self.isVisible():
            self.raise_()

    def open_settings_directly(self):
        # --- NEW: If already open and showing settings, close it back to the bubble ---
        if self.chat_panel.isVisible() and self.chat_panel.setting_panel.isVisible():
            self.chat_panel.hide()
            self.show()
            self.raise_()
            return

        # If the chat panel is closed, instantly snap it open to avoid animation delays
        if not self.chat_panel.isVisible():
            self.hide()
            target_x, target_y = self.calculate_chat_position()
            self.chat_panel.move(target_x, target_y)
            self.chat_panel.show()
            self.chat_panel.raise_()

        # Force the settings panel to be the visible widget
        self.chat_panel.content_stack.setCurrentWidget(self.chat_panel.setting_panel)
        self.chat_panel.raise_()
        self.chat_panel.activateWindow()

    def quit_app(self):
        self.tray_icon.hide()  # Cleanup icon from tray before exit to prevent ghosts
        QApplication.quit()

    def on_tray_icon_activated(self, reason):
        # Trigger equals a single Left Click
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_widget()

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
            "portalbig.png"
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

    def calculate_chat_position(self):
        bubble_x = self.x()
        bubble_y = self.y()

        screen = self.target_screen_geometry()
        panel_w = self.chat_panel.width()
        panel_h = self.chat_panel.height()

        target_x = bubble_x - 350
        target_y = bubble_y - 450

        # Prevent it from clipping past the edges of the same monitor as the bubble.
        min_x = screen.left()
        min_y = screen.top()
        max_x = screen.left() + screen.width() - panel_w
        max_y = screen.top() + screen.height() - panel_h

        target_x = max(min_x, min(target_x, max_x))
        target_y = max(min_y, min(target_y, max_y))

        return target_x, target_y

    def open_chat(self):
        target_x, target_y = self.calculate_chat_position()
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
            if self.widget_position_mode == "free":
                self.was_dragging = True
                self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.widget_position_mode != "free":
                self.apply_widget_position_mode()

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
        # Route through ChatPanel's own method instead of touching
        # chat_panel.browser directly. 
        self.chat_panel.reset_to_browser()
        self.chat_panel.hide()
        self.animation_window.shrink_from_to(start_rect, end_rect)

    def show_bubble_after_animation(self):
        self.show()
        self.raise_()