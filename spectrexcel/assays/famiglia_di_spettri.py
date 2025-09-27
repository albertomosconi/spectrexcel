from pathlib import Path
from typing import Tuple
from datetime import datetime

import pandas as pd
from PyQt6 import QtCore as core
from PyQt6 import QtWidgets as widgets
from xlsxwriter import Workbook, worksheet

from .shared import AssayWidget, parse_kd_file


class FamigliaDiSpettri(AssayWidget):
    df: pd.DataFrame

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

        title = widgets.QLabel("1. Upload a KD file")
        title.setStyleSheet("font: 16px; font-weight: bold;")
        layout.addWidget(title)

        button = widgets.QPushButton("select input file (.KD)")
        button.pressed.connect(self.__upload_clicked)
        layout.addWidget(button)

        box = widgets.QWidget()
        box.setDisabled(True)
        self.box = box
        layout.addWidget(box)

        layout = widgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(core.Qt.AlignmentFlag.AlignTop)
        box.setLayout(layout)

        title = widgets.QLabel("2. Create excel file")
        title.setStyleSheet("font: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.btn_save = widgets.QPushButton("generate excel")
        self.btn_save.pressed.connect(self.__btn_save_clicked)
        layout.addWidget(self.btn_save)

    def __upload_clicked(self):
        """"""
        try:
            filename, _ = widgets.QFileDialog.getOpenFileName(
                self,
                "Select a file",
                self.settings.value("cinetiche/folder_input", ".", type=str),
                "Kinetic Data Files (*.KD)",
            )
            if not filename:
                return

            self.path_file_input = Path(filename)
            self.settings.setValue(
                "famiglia_di_spettri/folder_input", str(self.path_file_input.parent)
            )
            self.log(f"selected {self.path_file_input}")

            self.log(f"loading {self.path_file_input.name}")
            if self.path_file_input.suffix.upper() != ".KD":
                raise Exception("unsupported input format")

            df = parse_kd_file(self.path_file_input)
            if df is None:
                raise Exception("failed to parse file")

            self.df = df

            self.box.setDisabled(False)
        except Exception as e:
            self.log(f"ERROR: {e}")

    def __btn_save_clicked(self):
        """"""
        try:
            filename_excel, _ = widgets.QFileDialog.getSaveFileName(
                self,
                "Save excel file",
                str(
                    Path(
                        self.settings.value(
                            "famiglia_di_spettri/folder_output", ".", type=str
                        )
                    )
                    / f"{datetime.now().strftime('%Y-%m-%d %H-%M-%S')} spectrexcel.xlsx"
                ),
                "Excel (*.xlsx)",
            )

            if not filename_excel:
                return

            self.log("generating excel file...")

            with pd.ExcelWriter(filename_excel, engine="xlsxwriter") as writer:
                wb: Workbook = writer.book
                ws: worksheet.Worksheet = wb.add_worksheet("data")

                chart = wb.add_chart({"type": "scatter", "subtype": "smooth"})
                if not chart:
                    return

                self.df.to_excel(
                    writer,
                    sheet_name="data",
                    index=True,
                    header=True,
                )

                for i in range(0, len(self.df.columns), 2):
                    chart.add_series(
                        {
                            "categories": ["data", 1, 0, len(self.df) + 1, 0],
                            "values": ["data", 1, 1 + i, len(self.df) + 1, 1 + i],
                            "line": {"width": 1},
                            "name": ["data", 0, 1 + i],
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
                        "min": 190,
                        "max": 1100,
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
                        "interval_unit": 0.05,
                        "min": 0,
                        "max": self.df.max().max(),
                        "major_tick_mark": "none",
                        "minor_tick_mark": "none",
                    }
                )
                chart.set_title(
                    {
                        "name": f"{self.path_file_input.stem}",
                        "name_font": {"color": "gray", "size": 14, "bold": False},
                    }
                )
                chart.set_size({"x_scale": 2, "y_scale": 2})
                chart.set_legend({"none": True})
                chart.set_style(5)

                ws.insert_chart(4, 4, chart=chart)

            self.log("excel file saved successfully")
        except Exception as e:
            print(e)
            self.log(f"ERROR: {e}")
