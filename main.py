import os

import subprocess
import sys

if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("org.ukrclassics.ukrclassics")

# Save the real Popen
_real_popen = subprocess.Popen

# Monkey-patch Popen
def _patched_popen(*args, **kwargs):
    if sys.platform == "win32":
        # always add “no window” flag
        cf = kwargs.get("creationflags", 0)
        kwargs["creationflags"] = cf | 0x08000000  # CREATE_NO_WINDOW

        # hide windows if startupinfo is used
        si = kwargs.get("startupinfo", subprocess.STARTUPINFO())
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = si

    return _real_popen(*args, **kwargs)

subprocess.Popen = _patched_popen

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