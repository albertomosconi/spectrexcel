import sys
import webbrowser
import importlib.metadata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Type

import requests
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
        BindingTitolazione,
        "",
    ),
    Assay(
        "cinetiche",
        Cinetiche,
        "",
    ),
    Assay(
        "famiglia di spettri",
        FamigliaDiSpettri,
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

        hbox_layout.addSpacerItem(
            widgets.QSpacerItem(10, 10, widgets.QSizePolicy.Policy.Expanding)
        )
        hbox_layout.addWidget(
            widgets.QLabel(f"version: {core.QCoreApplication.applicationVersion()}")
        )
        btn_check_update = widgets.QPushButton("check for updates")
        btn_check_update.setStyleSheet("font-weight: normal;")
        btn_check_update.pressed.connect(self.__check_and_download_update)
        hbox_layout.addWidget(btn_check_update)

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
        self.textbox.setStyleSheet("font-family: monospace; font-size: 14px;")
        self.textbox.setReadOnly(True)
        self.textbox.setFixedHeight(120)
        box.addWidget(self.textbox)

        info_label = widgets.QLabel(
            "developed by Alberto Mosconi ⋅ <a href='https://gitlab.com/albertomosconi/spectrexcel'>source code</a> ⋅ LICENSE: GPLv3 or later"
        )
        info_label.setOpenExternalLinks(True)
        box.addWidget(info_label)

        self.assay_dropdown.currentIndexChanged.emit(selected_assay)

        if self.__check_for_update():
            btn_check_update.setText("update available")
            btn_check_update_style = btn_check_update.style()
            if not btn_check_update_style:
                return
            icon = btn_check_update_style.standardIcon(
                widgets.QStyle.StandardPixmap.SP_BrowserReload
            )
            btn_check_update.setIcon(icon)

        self.show()

    def closeEvent(self, a0):
        if not a0:
            return
        self.settings.setValue("window/geometry", self.saveGeometry())
        a0.accept()

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

    def __check_for_update(self, do_log=True):
        try:
            if do_log:
                self.__log("checking for updates...")
            current_version = core.QCoreApplication.applicationVersion()

            response = requests.get(
                "https://gitlab.com/api/v4/projects/65488480/repository/tags?order_by=name&sort=desc"
            )
            if response.status_code != 200:
                if do_log:
                    self.__log("ERROR: unable to check for updates")
                return False

            releases = response.json()
            if len(releases) == 0:
                if do_log:
                    self.__log("no updates found")
                return False

            latest_release_version = releases[0]["name"]
            exists_newer_version = latest_release_version > f"v{current_version}"
            if not exists_newer_version:
                if do_log:
                    self.__log("no updates found")
                return False

            if do_log:
                self.__log(f"NEW APP VERSION FOUND: {latest_release_version}")
            self.latest_release_version = latest_release_version
            return True
        except Exception as e:
            if do_log:
                self.__log(f"ERROR: {e}")

    def __check_and_download_update(self):
        try:
            if not self.__check_for_update(do_log=False):
                return

            do_update = (
                widgets.QMessageBox.question(
                    self,
                    "Update found!",
                    "A new app version is available. Do you want to update?\n\nNOTE: this will close the app and open a new browser tab where the new executable will download automatically. Make sure to overwrite the existing one.",
                )
                == widgets.QMessageBox.StandardButton.Yes
            )
            if not do_update:
                self.__log("not updating")
                return

            self.__log(f"downloading update...")
            download_url = f"https://gitlab.com/albertomosconi/spectrexcel/-/raw/{self.latest_release_version}/dist/spectrexcel.exe"
            webbrowser.open(download_url)

            sys.exit(0)
        except Exception as e:
            self.__log(f"ERROR: {e}")


def main():
    app = widgets.QApplication(sys.argv)

    core.QCoreApplication.setOrganizationName("magichemistry")
    core.QCoreApplication.setApplicationName("spectrexcel")

    try:
        version = importlib.metadata.version("spectrexcel")
    except importlib.metadata.PackageNotFoundError:
        version = "UNKNOWN"

    core.QCoreApplication.setApplicationVersion(version)

    MainWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
