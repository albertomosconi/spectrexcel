from datetime import datetime
from pathlib import Path
from typing import Tuple

import pandas as pd
from PyQt6 import QtCore as core
from PyQt6 import QtGui as gui
from PyQt6 import QtWidgets as widgets
from xlsxwriter import Workbook, worksheet

from .shared import AssayWidget, parse_kd_file, parse_txt_file


class Cinetiche(AssayWidget):
    dfs: list[Tuple[str, pd.DataFrame]] = []

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

        title = widgets.QLabel("2. Configure parameters")
        title.setStyleSheet("font: 16px; font-weight: bold;")
        layout.addWidget(title)

        form_settings = widgets.QWidget()
        form_layout = widgets.QFormLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_settings.setLayout(form_layout)
        layout.addWidget(form_settings)

        self.wlen_read = widgets.QLineEdit()
        self.wlen_read.setText("300")
        onlyInt = gui.QIntValidator()
        self.wlen_read.setValidator(onlyInt)
        form_layout.addRow("reading wavelength", self.wlen_read)

        self.wlen_correction = widgets.QLineEdit()
        self.wlen_correction.setText("800")
        onlyInt = gui.QIntValidator()
        self.wlen_correction.setValidator(onlyInt)
        form_layout.addRow("correction wavelength", self.wlen_correction)

        title = widgets.QLabel("3. Create excel file")
        title.setStyleSheet("font: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.btn_save = widgets.QPushButton("generate excel")
        self.btn_save.pressed.connect(self.__btn_save_clicked)
        layout.addWidget(self.btn_save)

    def __upload_clicked(self):
        """"""

        filenames, _ = widgets.QFileDialog.getOpenFileNames(
            self,
            "Select multiple files",
            self.settings.value("cinetiche/folder_input", ".", type=str),
            "Kinetic Data Files (*.KD)",
        )
        if len(filenames) == 0:
            return

        self.settings.setValue("cinetiche/folder_input", str(Path(filenames[0]).parent))
        self.log(f"selected {len(filenames)} files")

        for filename in filenames:
            filepath = Path(filename)
            self.log(f"loading {filepath.name}")

            if filepath.suffix.upper() == ".KD":
                df = parse_kd_file(filepath)
            # elif self.path_file_input.suffix.upper() == ".TXT":
            #     self.df = parse_txt_file(self.path_file_input)
            else:
                self.log("ERROR: unknown input format")
                continue

            if df is None:
                self.log("ERROR: failed to parse file")
                continue

            self.dfs.append((filepath.stem, df))

            # self.df, did_clean = clean_duplicate_spectra(self.df)
            # if did_clean:
            #     self.log("deleted duplicate spectra")

            # self.log(f"the file contains {len(self.df)} signals")

        self.box.setDisabled(False)

    def __btn_save_clicked(self):
        """"""

        filename_excel, _ = widgets.QFileDialog.getSaveFileName(
            self,
            "Save excel file",
            str(
                Path(self.settings.value("cinetiche/folder_output", ".", type=str))
                / f"{datetime.now().strftime("%Y-%m-%d %H-%M-%S")} spectrexcel.xlsx"
            ),
            "Excel (*.xlsx)",
        )

        if not filename_excel:
            return

        self.settings.setValue(
            "cinetiche/folder_output", str(Path(filename_excel).parent)
        )

        self.log("generating excel file...")

        # sort uploaded files by name
        self.dfs.sort(key=lambda t: t[0])

        wl_read = int(self.wlen_read.text())
        wl_corr = int(self.wlen_correction.text())

        with pd.ExcelWriter(filename_excel, engine="xlsxwriter") as writer:
            wb: Workbook = writer.book
            ws: worksheet.Worksheet = wb.add_worksheet("data")

            ws.write(0, 0, "tracce")
            ws.write(1, 0, "Time (s)")

            for col_num, value in enumerate(self.dfs[0][1].columns.values):
                ws.write(col_num + 2, 0, float(value))

            chart = wb.add_chart({"type": "scatter", "subtype": "smooth"})
            if not chart:
                return

            chart.set_title(
                {
                    "name": "trends",
                    "name_font": {"color": "gray", "size": 14, "bold": False},
                }
            )

            for i, (filename, spectra_df) in enumerate(self.dfs):
                spectra_read = spectra_df.loc[[wl_read]].squeeze()
                spectra_corr = spectra_df.loc[[wl_corr]].squeeze()

                final: pd.Series = spectra_read - spectra_corr

                final.to_excel(
                    writer,
                    sheet_name="data",
                    index=False,
                    header=False,
                    startrow=2,
                    startcol=1 + i,
                )
                ws.write(1, 1 + i, filename)

                chart.add_series(
                    {
                        "categories": ["data", 2, 0, len(final) + 2, 0],
                        "values": ["data", 2, 1 + i, len(final), 1 + i],
                        "line": {"width": 1.25},
                        "name": ["data", 1, 1 + i],
                    }
                )

            chart.set_x_axis(
                {
                    "name": "Time (s)",
                    "name_font": {"bold": False, "color": "gray"},
                    "position_axis": "on_tick",
                    "num_font": {"color": "gray"},
                    "line": {"color": "gray"},
                    "interval_unit": 50,
                    "min": 0,
                    "max": 300,
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
                    "max": 0.35,
                    "major_tick_mark": "none",
                    "minor_tick_mark": "none",
                }
            )
            chart.set_size({"x_scale": 1.5, "y_scale": 1.5})
            chart.set_legend(
                {"position": "bottom", "font": {"color": "gray", "size": 9}}
            )

            chart.set_style(5)
            ws.insert_chart(4, 4 + len(self.dfs), chart=chart)

        self.log("excel file saved successfully")
