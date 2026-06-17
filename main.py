import sys
from PySide6.QtWidgets import QApplication

from app.widget import FloatingWidget


# This starts the entire app
app = QApplication(sys.argv)

# Create and show the floating bubble
widget = FloatingWidget()
widget.show()

# Keep the app running
sys.exit(app.exec())