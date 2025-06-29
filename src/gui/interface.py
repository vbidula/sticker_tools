# mapping from status keys to display texts
import sys
import os

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QLineEdit, QSizePolicy,
    QPushButton, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QMovie
from PyQt6.QtCore import QSize


from ..sticker_tools.patch_duration import patch_duration
from ..sticker_tools.convert_optimize import convert_optimize


class WorkerThread(QThread):
    # signal: status key, error message (None on success)
    finished = pyqtSignal(str, object)
    progress = pyqtSignal(int)

    def __init__(self, func, *args):
        super().__init__()
        self.func = func
        self.args = args

    def _on_progress(self, value: int):
        """Emit progress updates to the main thread."""
        self.progress.emit(value)

    def run(self):
        try:
            # call function, providing progress callback if supported
            try:
                self.func(*self.args, progress_callback=self._on_progress)
            except TypeError:
                # fallback if the function doesn't accept progress_callback
                self.func(*self.args)
            self.finished.emit("success", None)
        except Exception as e:
            self.finished.emit("error", e)


STATUS_DESCRIPTIONS = {
 "waiting_for_file": "Завантажте файл",
 "waiting_for_command": "Виберіть команду",
 "processing": "Працюю над стікером, зачекайте...",
 "success": "Готово!\nМожете завантажити ще один файл",
 "error": "Ой-ой, щось пішло не так...",
}

NAME = "Українська Класика"
VERSION = "1.0"


class FileLineEdit(QLineEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setText("Перетягніть файл або натисніть для пошуку")
        self.setAcceptDrops(True)
        # center text and fix square size
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # allow full-width expansion, fix height
        self.setFixedHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            path, _ = QFileDialog.getOpenFileName(self, "Виберіть файл")
            if path:
                self.setText(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            # take only the first file
            path = QUrl(urls[0]).toLocalFile()
            self.setText(path)
        event.acceptProposedAction()


class FilePatcherApp(QWidget):
    def __init__(self):
        super().__init__()
        # prepare quantized progress lights for status bar
        self._progress_steps = []
        for _ in range(10):
            light = QLabel(self)
            light.setFixedSize(5, 5)
            light.setStyleSheet("background-color: lightgray; border-radius: 2px;")
            self._progress_steps.append(light)
        layout = QVBoxLayout(self)
        # base directory for relative resources
        self._base_dir = os.path.dirname(os.path.abspath(__file__))
        self.setWindowTitle(f"{NAME} v{VERSION}")

        self.resize(400, 400)
        self.setFixedSize(400, 400)

        # keep references to worker threads to prevent premature destruction
        self._workers = []

        # top area: status & progress on left, separator, help & contacts on right
        top_layout = QHBoxLayout()

        # left column: status animation + description
        left_col = QVBoxLayout()
        # status row: animation + description
        self.status_movie_label = QLabel(self)
        fm = self.fontMetrics()
        h = fm.height()
        size = 3 * h
        self.status_movie_label.setFixedSize(size, size)
        self.status_movie_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_desc = QLabel("")
        self.status_desc.setWordWrap(True)
        self.status_desc.setFixedHeight(size)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status_movie_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        status_row.addWidget(self.status_desc, alignment=Qt.AlignmentFlag.AlignVCenter)
        left_col.addLayout(status_row)

        top_layout.addLayout(left_col, 1)

        # vertical separator
        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setLineWidth(1)
        top_layout.addWidget(separator)

        # right column: help and contacts buttons
        self.help_btn = QPushButton()
        help_btn_icon = QIcon(os.path.join(self._base_dir, "icons", "information-outline.svg"))
        self.help_btn.setIcon(help_btn_icon)
        self.help_btn.setIconSize(QSize(16, 16))
        self.help_btn.clicked.connect(self.show_help)
        # make help button shrink to its content
        self.help_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.contacts_btn = QPushButton()
        contacts_btn_icon = QIcon(os.path.join(self._base_dir, "icons", "bug-outline.svg"))
        self.contacts_btn.setIcon(contacts_btn_icon)
        self.contacts_btn.setIconSize(QSize(16, 16))
        self.contacts_btn.clicked.connect(self.show_contacts)
        # make contacts button shrink to its content
        self.contacts_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        right_col = QVBoxLayout()
        right_col.addWidget(self.help_btn)
        right_col.addWidget(self.contacts_btn)
        right_col.addStretch()
        top_layout.addLayout(right_col, 0)

        # default status animation (play invoked inside set_status)
        self.set_status("waiting_for_file")
        # add the composed top layout
        layout.addLayout(top_layout)

        # file selector widget
        self.file_edit = FileLineEdit()
        layout.addWidget(self.file_edit)

        # quantized progress lights (10 steps) below the text field
        progress_bar = QHBoxLayout()
        for light in self._progress_steps:
            progress_bar.addWidget(light, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(progress_bar)

        # buttons
        self.btn_patch = QPushButton("Пропатчити")
        self.btn_convert_patch = QPushButton("Конвертувати + Пропатчити")
        layout.addWidget(self.btn_patch)
        layout.addWidget(self.btn_convert_patch)

        # disable both buttons initially
        self.btn_patch.setEnabled(False)
        self.btn_convert_patch.setEnabled(False)

        self.btn_patch.clicked.connect(self.do_patch)
        self.btn_convert_patch.clicked.connect(self.do_convert_and_patch)

        # update buttons when a file is selected or changed
        self.file_edit.textChanged.connect(self._update_buttons_state)

    def _get_path(self):
        path = self.file_edit.text()
        if not path:
            QMessageBox.warning(self, "No file", "Please select a file first!")
        return path

    def do_patch(self):
        path = self._get_path()
        if not path:
            return
        self.set_status("processing")
        # disable buttons while working
        self.btn_patch.setEnabled(False)
        self.btn_convert_patch.setEnabled(False)
        self.set_progress(0)
        worker = WorkerThread(patch_duration, path)
        worker.finished.connect(self._on_worker_finished)
        # update status based on worker result
        worker.finished.connect(lambda status, err: self.set_status(status))
        # clean up thread object when done
        worker.finished.connect(worker.deleteLater)
        self._workers.append(worker)
        worker.start()

    def do_convert_and_patch(self):
        path = self._get_path()
        if not path:
            return
        self.set_status("processing")
        self.btn_patch.setEnabled(False)
        self.btn_convert_patch.setEnabled(False)
        self.set_progress(0)
        def task_convert_and_patch(p, progress_callback=None):
            output = os.path.splitext(p)[0] + ".webm"
            convert_optimize(p, progress_callback=progress_callback)
            patch_duration(output)
        worker = WorkerThread(task_convert_and_patch, path)
        worker.finished.connect(self._on_worker_finished)
        # update status based on worker result
        worker.finished.connect(lambda status, err: self.set_status(status))
        # connect progress signal to update progress lights
        worker.progress.connect(self.set_progress)
        # clean up thread object when done
        worker.finished.connect(worker.deleteLater)
        self._workers.append(worker)
        worker.start()

    def _update_buttons_state(self, path: str):
        """Enable the correct button based on file extension."""
        ext = path.lower().rsplit('.', 1)[-1] if '.' in path else ''
        if ext == 'webm':
            self.btn_patch.setEnabled(True)
            self.btn_convert_patch.setEnabled(False)
        else:
            self.btn_patch.setEnabled(False)
            self.btn_convert_patch.setEnabled(True)
        if path:
            self.set_status("waiting_for_command")

    def show_help(self):
        instructions = (
            "Варто знати:\n\n"
            "1. Ця програма не вміє вирізати стікери з відео. Припускається, що у вас вже є обрізане відео у правильній "
            "роздільній здатності - 512х512 пікселів і не більше 30 fps.\n\n"
            "2. Ваш файл може бути в .mp4, .mov, .avi або .mkv. У вас зʼявиться можливість "
            "\"конвертувати\" ваш файл в .webm формат. При цьому програма підбере найкращі параметри аби стікер виглядав "
            "якнайкраще при обмеженні в 256 кб. Конвертація може зайняти від кількох секунд до кількох хвилин - залежить "
            "від вхідного відео.\n\n"
            "3. Якщо файл уже конвертовано в .webm - зʼявиться кнопка \"пропатчити\" "
            "(також автоматично застосовується після конвертації) редагує метадані вашого "
            "стікера щоб замаскувати справжню тривалість. Таким чином, телеграм дозволить вам додати стікери, що тривають "
            "більше трьох секунд. \n"
            
            "\n\n"
            "Інструкції:\n\n"
            "1. Виберіть файл перетягуванням або в меню, що зʼявиться після натискання на біле поле.\n\n"
            "2. Натисніть одну з кнопок внизу (одна з них стане доступна після додавання файла)\n\n"
            "3. Новий файл буде збережено в тій самій папці де знаходився ваш оригінальний файл."
        )
        QMessageBox.information(self, "Інструкція", instructions)

    def show_contacts(self):
        """Display the software author's contact information."""
        contacts = "У випадку проблеми можете надіслати листа з описом на адресу:\n\nukrclassics@pm.me"
        QMessageBox.information(self, "Контакт", contacts)

    def set_status(self, status: str):
        # update description label from mapping
        desc = STATUS_DESCRIPTIONS.get(status, status.capitalize())
        self.status_desc.setText(desc)
        # load and loop the corresponding GIF animation
        gif_path = os.path.join(self._base_dir, "status_animations", f"{status}.gif")
        movie = QMovie(gif_path)
        movie.setCacheMode(QMovie.CacheMode.CacheAll)
        fm = self.fontMetrics()
        size = 3 * fm.height()
        movie.setScaledSize(QSize(size, size))
        self.status_movie_label.setMovie(movie)
        movie.start()

    def _on_worker_finished(self, status, err):
        self.set_status(status)
        # re-enable buttons after processing
        self._update_buttons_state(self.file_edit.text())
        # reset progress lights after completion or error
        self.set_progress(0)
        if err:
            error_text = (
                         "На жаль, сталася помилка. Перевірте чи ваше відео відповідає вимогам:\n\n"
                         "1) Роздільна здатність не більше 512x512 пікселів\n"
                         "2) Кількість кадрів на секунду не більше 30\n"
                         "3) Правильний формат файлу - mp4 або схожий\n\n"
                     ) + str(err)
            QMessageBox.critical(self, "Помилка", error_text)

    def set_progress(self, count: int):
        """Light up the first `count` progress steps."""
        total = len(self._progress_steps)
        for i, light in enumerate(self._progress_steps):
            if i < count:
                light.setStyleSheet("background-color: #20d420; border-radius: 2px;")
            else:
                light.setStyleSheet("background-color: lightgray; border-radius: 2px;")