from pathlib import Path

import pandas as pd
from PyQt6 import QtCore as core
from PyQt6 import QtWidgets as widgets
from xlsxwriter import Workbook, worksheet

from .shared import AssayWidget, clean_duplicate_spectra, parse_sd_file, parse_txt_file


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

        title = widgets.QLabel("1. Upload a TXT or SD file")
        title.setStyleSheet("font: 16px; font-weight: bold;")
        layout.addWidget(title)

        button = widgets.QPushButton("select input file (.txt .SD)")
        button.pressed.connect(self.__upload_clicked)
        layout.addWidget(button)

        self.title2 = widgets.QLabel("2. Create excel file")
        self.title2.setDisabled(True)
        self.title2.setStyleSheet("font: 16px; font-weight: bold;")
        layout.addWidget(self.title2)

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
            "Spectra Files (*.txt *.SD)",
        )
        if not filename:
            return

        self.path_file_input = Path(filename)
        self.settings.setValue("main/folder_input", str(self.path_file_input.parent))
        self.log(f"selected {self.path_file_input}")

        if self.path_file_input.suffix.upper() == ".SD":
            self.df = parse_sd_file(self.path_file_input)
        elif self.path_file_input.suffix.upper() == ".TXT":
            self.df = parse_txt_file(self.path_file_input)
        else:
            self.log("ERROR: unknown input format")
            return

        self.df, did_clean = clean_duplicate_spectra(self.df)
        if did_clean:
            self.log("deleted duplicate spectra")

        self.log(f"the file contains {len(self.df)} signals")

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

        if "Std.Dev." in self.df.columns:
            self.log("deleting std.dev. columns...")
            self.df = self.df.drop("Std.Dev.", axis=1)

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
            if not chart:
                return

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
            ws.insert_chart(len(self.df) + 2, 1, chart=chart)

        self.log("excel file saved successfully")
