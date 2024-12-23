import re
from pathlib import Path
from typing import Callable

import pandas as pd
from PyQt6 import QtCore as core
from PyQt6 import QtWidgets as widgets
from xlsxwriter import Workbook, worksheet

# from superqt import QRangeSlider, QLabeledDoubleRangeSlider

from .shared import AssayWidget


class BindingTitolazione(AssayWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # load settings
        self.settings = core.QSettings(
            core.QCoreApplication.organizationName(),
            core.QCoreApplication.applicationName(),
        )

        layout = widgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(core.Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

        title = widgets.QLabel("1. Upload a txt file")
        title.setStyleSheet("font: 16px; font-weight: bold;")
        layout.addWidget(title)

        button = widgets.QPushButton("select input file (.txt)")
        button.pressed.connect(self.__upload_clicked)
        layout.addWidget(button)

        self.title2 = widgets.QLabel("2. Create excel file")
        self.title2.setDisabled(True)
        self.title2.setStyleSheet("font: 16px; font-weight: bold;")
        layout.addWidget(self.title2)

        # self.xrange = QLabeledDoubleRangeSlider(core.Qt.Orientation.Horizontal)
        # box.addWidget(self.xrange)

        self.btn_save = widgets.QPushButton("generate excel")
        self.btn_save.setDisabled(True)
        self.btn_save.pressed.connect(self.__btn_save_clicked)
        layout.addWidget(self.btn_save)

    def __upload_clicked(self):
        """"""

        filename, _ = widgets.QFileDialog.getOpenFileName(
            self,
            "Select a File",
            self.settings.value("main/folder_input", ".", type=str),
            "Text (*.txt)",
        )
        if not filename:
            return

        self.path_file_input = Path(filename)
        self.settings.setValue("main/folder_input", str(self.path_file_input.parent))
        self.log(f"selected {self.path_file_input}")

        with self.path_file_input.open("r") as fp:
            contents = fp.read()

        contents = re.sub(r"[ \t]+", " ", contents.strip())
        contents = contents.split("\n")

        # TODO: validate file format

        first_line = contents[0]
        first_line = re.sub(r"<(\d+) nm>", r"\g<1>", first_line)
        columns = first_line[1:-1].split('" "')
        data = [columns, *[line.split(" ") for line in contents[1:]]]

        self.df = pd.DataFrame(
            data=[line.split(" ") for line in contents[1:]],
            columns=columns,
        )
        self.df = self.df.drop("WL Result", axis=1)

        halfway_row = int(len(self.df) / 2)
        df_data = self.df.drop("#Sample", axis=1)
        df_1st_half = df_data.head(halfway_row).reset_index(drop=True)
        df_2nd_half = df_data.tail(halfway_row).reset_index(drop=True)

        if df_1st_half.equals(df_2nd_half):
            self.df = self.df.head(halfway_row)
            self.log("deleted duplicate spectra")
        else:
            pass
        self.log(f"the file contains {len(self.df)} signals")

        self.df = self.df.apply(pd.to_numeric)

        self.log("deleting std.dev. columns...")
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
            str(
                Path(self.settings.value("main/folder_output", ".", type=str))
                / f"{self.path_file_input.stem}.xlsx"
            ),
            "Excel (*.xlsx)",
        )

        if not filename_excel:
            return

        self.settings.setValue("main/folder_output", str(Path(filename_excel).parent))

        self.log("generating excel file...")
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

        self.log("excel file saved successfully")
