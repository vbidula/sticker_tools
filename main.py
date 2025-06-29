import os
import sys

if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("org.ukrclassics.ukrclassics")


from src.gui.interface import FilePatcherApp, QApplication, QIcon, QSize

if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    app = QApplication(sys.argv)
    # ico  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "gui", "appicons", "app.ico")  # use your largest .ico
    path = os.path.abspath(os.path.join(base_dir, "src", "gui", "appicons", "app.ico"))
    icon = QIcon(path)
    app.setWindowIcon(icon)
    w = FilePatcherApp()
    w.show()
    w.setWindowIcon(icon)
    sys.exit(app.exec())