import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from PyQt6 import QtCore as core
from PyQt6 import QtGui as gui
from PyQt6 import QtWidgets as widgets
from xlsxwriter import Workbook, worksheet

# from superqt import QRangeSlider, QLabeledDoubleRangeSlider


class MainWindow(widgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.file_path: Path | None = None

        self.setWindowTitle("raw spectrophotometer data to excel")
        pixmap = gui.QPixmap()
        pixmap.loadFromData((Path(__file__).parent / "icon.ico").read_bytes())
        self.setWindowIcon(gui.QIcon(pixmap))

        tabs = widgets.QTabWidget()
        self.setCentralWidget(tabs)
        self.setFixedSize(core.QSize(800, 500))
        # self.setMinimumSize(core.QSize(800, 400))

        page_main = widgets.QWidget()
        box = widgets.QVBoxLayout()
        box.setAlignment(core.Qt.AlignmentFlag.AlignTop)
        page_main.setLayout(box)
        tabs.addTab(page_main, "generate excel")

        title = widgets.QLabel("1. Upload a txt file")
        title.setStyleSheet("font: 18px; font-weight: bold;")
        box.addWidget(title)

        button = widgets.QPushButton("select input file (.txt)")
        button.pressed.connect(self.__upload_clicked)
        box.addWidget(button)

        self.title2 = widgets.QLabel("2. Create excel file")
        self.title2.setDisabled(True)
        self.title2.setStyleSheet("font: 18px; font-weight: bold;")
        box.addWidget(self.title2)

        # self.xrange = QLabeledDoubleRangeSlider(core.Qt.Orientation.Horizontal)
        # box.addWidget(self.xrange)

        self.btn_save = widgets.QPushButton("generate")
        self.btn_save.setDisabled(True)
        self.btn_save.pressed.connect(self.__btn_save_clicked)
        box.addWidget(self.btn_save)

        self.textbox = widgets.QTextEdit()
        self.textbox.setReadOnly(True)
        box.addWidget(self.textbox)

        page_settings = widgets.QWidget()
        box = widgets.QVBoxLayout()
        box.setAlignment(core.Qt.AlignmentFlag.AlignTop)
        box.addStretch()
        page_settings.setLayout(box)
        tabs.addTab(page_settings, "settings")

        text_info = widgets.QLabel("developed by Alberto Mosconi")
        box.addWidget(text_info)

        self.show()

    def __upload_clicked(self):
        """"""

        filename, _ = widgets.QFileDialog.getOpenFileName(
            self, "Select a File", ".", "Text (*.txt)"
        )
        if not filename:
            return

        self.textbox.clear()

        self.file_path = Path(filename)
        self.__log(f"selected {self.file_path}")

        with self.file_path.open("r") as fp:
            contents = fp.read()

        contents = re.sub(r"[ \t]+", " ", contents.strip())
        contents = contents.split("\n")

        first_line = contents[0]
        first_line = re.sub(r"<(\d+) nm>", r"\g<1>", first_line)
        columns = first_line[1:-1].split('" "')
        data = [columns, *[line.split(" ") for line in contents[1:]]]

        self.df = pd.DataFrame(
            data=[line.split(" ") for line in contents[1:]],
            columns=columns,
        )
        self.df = self.df.drop("WL Result", axis=1)

        self.__log("checking if spectra are duplicated...")

        halfway_row = int(len(self.df) / 2)
        df_data = self.df.drop("#Sample", axis=1)
        df_1st_half = df_data.head(halfway_row).reset_index(drop=True)
        df_2nd_half = df_data.tail(halfway_row).reset_index(drop=True)

        if df_1st_half.equals(df_2nd_half):
            self.__log("found duplicate data, cleaning...")
            self.df = self.df.head(halfway_row)
            self.__log("successfully deleted duplicate spectra")
        else:
            self.__log("found no duplicates")
        self.__log(f"the file contains {len(self.df)} signals")

        self.__log("converting values to numeric...")
        self.df = self.df.apply(pd.to_numeric)

        self.__log("deleting std.dev. columns...")
        self.df = self.df.drop("Std.Dev.", axis=1)

        # abs_min = df_data.drop(0, axis=0).min()
        # print(abs_min)

        # self.xrange.setRange(0.0, 2.0)
        # self.xrange.setValue((0.0, 0.5))

        self.title2.setDisabled(False)
        self.btn_save.setDisabled(False)

    def __btn_save_clicked(self):
        """"""

        filename_excel, _ = widgets.QFileDialog.getSaveFileName(
            self,
            "Save excel file",
            str(self.file_path.with_suffix(".xlsx")),
            "Excel (*.xlsx)",
        )

        self.__log("generating excel file...")
        with pd.ExcelWriter(filename_excel, engine="xlsxwriter") as writer:
            self.df.to_excel(
                writer, sheet_name="data", index=False, header=False, startrow=1
            )

            wb: Workbook = writer.book
            ws: worksheet.Worksheet = writer.sheets["data"]

            ws.write(0, 0, self.df.columns[0])
            for col_num, value in enumerate(self.df.columns[1:].values):
                ws.write(0, col_num + 1, int(value))

            chart = wb.add_chart({"type": "scatter", "subtype": "smooth"})

            for i in range(len(self.df)):
                chart.add_series(
                    {
                        "categories": ["data", 0, 1, 0, len(self.df.columns)],
                        "values": ["data", i + 1, 1, i + 1, len(self.df.columns)],
                        "line": {"width": 1.25},
                    }
                )
            chart.set_x_axis(
                {
                    "name": "λ (nm)",
                    "name_font": {"bold": False, "color": "gray"},
                    "position_axis": "on_tick",
                    "num_font": {"color": "gray"},
                    "line": {"color": "gray"},
                    "interval_unit": 50,
                    "min": 200,
                    "max": 800,
                    "major_tick_mark": "none",
                    "minor_tick_mark": "none",
                }
            )
            chart.set_y_axis(
                {
                    "name": "Abs (AU)",
                    "name_font": {"bold": False, "color": "gray"},
                    "num_font": {"color": "gray"},
                    "num_format": "#,##0.00",
                    "line": {"color": "gray"},
                    "major_gridlines": {"visible": False},
                    "min": 0,
                    "max": 0.5,
                    "major_tick_mark": "none",
                    "minor_tick_mark": "none",
                }
            )
            chart.set_size({"x_scale": 1.5, "y_scale": 1.5})
            chart.set_legend({"position": "none"})

            chart.set_style(5)
            ws.insert_chart(f"C5", chart)

        self.__log("excel file saved successfully")

    def __log(self, text: str | list[str]):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(text, str):
            self.textbox.append(f"[ {ts} ] {text}")
        elif isinstance(text, list):
            self.textbox.append(*[f"[ {ts} ] {t}" for t in text])


if __name__ == "__main__":
    app = widgets.QApplication(sys.argv)
    w = MainWindow()
    app.exec()
