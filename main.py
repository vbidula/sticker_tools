import sys
from src.gui.interface import FilePatcherApp, QApplication

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = FilePatcherApp()
    w.show()
    sys.exit(app.exec())