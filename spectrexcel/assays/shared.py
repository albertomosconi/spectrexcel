from typing import Callable

from PyQt6 import QtWidgets as widgets


class AssayWidget(widgets.QWidget):
    def __init__(self, log: Callable[[str | list[str]], None]):
        super().__init__()

        self.log = log
