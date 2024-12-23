import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Type

from PyQt6 import QtCore as core
from PyQt6 import QtGui as gui
from PyQt6 import QtWidgets as widgets

from spectrexcel.assays import *


@dataclass
class Assay:
    name: str
    widget: Type[AssayWidget]
    description: str


ASSAYS = [
    Assay(
        "binding / titolazione",
        titolazione.BindingTitolazione,
        "",
    ),
]


class MainWindow(widgets.QMainWindow):
    def __init__(self):
        super().__init__()

        # initial setup
        self.setWindowTitle("SpectrExcel")
        self.setFixedSize(core.QSize(800, 500))

        # set application icon
        pixmap = gui.QPixmap()
        pixmap.loadFromData((Path(__file__).parent / "icon.png").read_bytes())
        self.setWindowIcon(gui.QIcon(pixmap))

        # load settings
        self.settings = core.QSettings(
            core.QCoreApplication.organizationName(),
            core.QCoreApplication.applicationName(),
        )
        geometry = self.settings.value(
            "window/geometry", core.QByteArray(), type=core.QByteArray
        )
        screen = self.screen()
        if screen is None:
            self.move(0, 0)
        elif geometry.isEmpty():
            available_geometry = screen.availableGeometry()
            self.move(
                (available_geometry.width() - self.width()) // 2,
                (available_geometry.height() - self.height()) // 2,
            )
        else:
            self.restoreGeometry(geometry)

        page_main = widgets.QWidget()
        self.setCentralWidget(page_main)
        box = widgets.QVBoxLayout()
        self.box = box
        box.setAlignment(core.Qt.AlignmentFlag.AlignTop)
        page_main.setLayout(box)

        hbox = widgets.QWidget()
        hbox_layout = widgets.QHBoxLayout()
        hbox_layout.setContentsMargins(0, 0, 0, 0)
        hbox_layout.setAlignment(core.Qt.AlignmentFlag.AlignLeft)
        hbox.setLayout(hbox_layout)
        box.addWidget(hbox)

        hbox_layout.addWidget(widgets.QLabel("select assay: "))

        self.assay_dropdown = widgets.QComboBox()
        self.assay_dropdown.addItems(map(lambda a: a.name, ASSAYS))
        selected_assay = self.settings.value("main/selected_assay", 0, type=int)
        if selected_assay >= len(ASSAYS):
            selected_assay = 0
        self.assay_dropdown.setCurrentIndex(selected_assay)
        self.assay_dropdown.currentIndexChanged.connect(self.__handle_assay_dropdown)
        hbox_layout.addWidget(self.assay_dropdown)

        self.assay_description = widgets.QLabel(
            ASSAYS[self.assay_dropdown.currentIndex()].description
        )
        self.assay_description.setWordWrap(True)
        box.addWidget(self.assay_description)

        line = widgets.QFrame()
        line.setFrameShape(widgets.QFrame.Shape.HLine)
        line.setFrameShadow(widgets.QFrame.Shadow.Sunken)
        box.addWidget(line)

        box.addItem(widgets.QSpacerItem(0, 20))

        self.assay_widget = widgets.QWidget()
        box.addWidget(self.assay_widget)

        box.addStretch()

        self.textbox = widgets.QTextEdit()
        self.textbox.setReadOnly(True)
        self.textbox.setFixedHeight(120)
        box.addWidget(self.textbox)

        info_label = widgets.QLabel(
            "developed by Alberto Mosconi ⋅ <a href='https://gitlab.com/albertomosconi/spectrexcel'>source code</a> ⋅ LICENSE: GPLv3 or later"
        )
        info_label.setOpenExternalLinks(True)
        box.addWidget(info_label)

        self.assay_dropdown.currentIndexChanged.emit(selected_assay)

        self.show()

    def closeEvent(self, event):
        self.settings.setValue("window/geometry", self.saveGeometry())
        event.accept()

    def __handle_assay_dropdown(self, index: int):
        self.assay_description.setText(ASSAYS[index].description)

        assay_widget = ASSAYS[index].widget(self.__log)
        self.box.replaceWidget(self.assay_widget, assay_widget)
        self.assay_widget.close()
        self.assay_widget = assay_widget

        self.__log(f"LOADED ASSAY: {ASSAYS[index].name}")

        self.settings.setValue("main/selected_assay", index)

    def __log(self, text: str | list[str]):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(text, str):
            self.textbox.append(f"[ {ts} ] {text}")
        elif isinstance(text, list):
            self.textbox.append(*[f"[ {ts} ] {t}" for t in text])


def main():
    app = widgets.QApplication(sys.argv)

    core.QCoreApplication.setOrganizationName("magichemistry")
    core.QCoreApplication.setApplicationName("spectrexcel")

    MainWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
