"""Application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import ctypes


from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ui.views.login_dialog import LoginDialog
from ui.views.main_window import MainWindow
from logic.file_lock import AlreadyRunningError, SingleInstanceLock


def main() -> int:
    try:
        myappid = 'mycompany.dfxtester.ate.v1' # מזהה ייחודי כלשהו
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception as e:
        print(f"Note: Could not set AppUserModelID: {e}")

    app = QApplication(sys.argv)
    icon_path = Path(__file__).resolve().parent / "ui" / "assets" / "icons" / "BirdAppIcon.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    else:
        print(f"Warning: Icon not found at {icon_path}") # הדפסה לדיבאג
    
    lock_path = Path(__file__).resolve().parent / "data" / "app.lock"
    lock = SingleInstanceLock(lock_path)
    try:
        lock.acquire()
    except AlreadyRunningError as exc:
        QMessageBox.critical(None, "DFX Tester", str(exc))
        return 1

    try:
        login = LoginDialog()
        if login.exec():
            user_info = login.get_user_info()
            window = MainWindow(user_info)
            window.show()
            return app.exec()
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
