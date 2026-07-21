from datetime import datetime
from pathlib import Path

import dearpygui.dearpygui as dpg
import pandas as pd
from xlsxwriter import Workbook, worksheet

from spectrexcel.i18n import _

from .parsing import WAVELENGTH_MAX, WAVELENGTH_MIN, parse_kd_file
from .view import AssayView


def export_spectrum_family(
    dataframe: pd.DataFrame, input_path: Path, output_path: Path
) -> None:
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        workbook: Workbook = writer.book
        sheet: worksheet.Worksheet = workbook.add_worksheet("data")
        chart = workbook.add_chart({"type": "scatter", "subtype": "smooth"})
        dataframe.to_excel(writer, sheet_name="data", index=True, header=True)

        for column in range(0, len(dataframe.columns), 2):
            chart.add_series(
                {
                    "categories": ["data", 1, 0, len(dataframe), 0],
                    "values": ["data", 1, 1 + column, len(dataframe), 1 + column],
                    "line": {"width": 1},
                    "name": ["data", 0, 1 + column],
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
                "min": WAVELENGTH_MIN,
                "max": WAVELENGTH_MAX,
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
                "max": float(dataframe.max().max()),
                "major_tick_mark": "none",
                "minor_tick_mark": "none",
            }
        )
        chart.set_title(
            {
                "name": input_path.stem,
                "name_font": {"color": "gray", "size": 14, "bold": False},
            }
        )
        chart.set_size({"x_scale": 2, "y_scale": 2})
        chart.set_legend({"none": True})
        chart.set_style(5)
        sheet.insert_chart(4, 4, chart=chart)


class FamigliaDiSpettri(AssayView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dataframe: pd.DataFrame | None = None
        self.input_path: Path | None = None

    def build(self, parent: str) -> None:
        px = self.display_scale.pixels
        title = dpg.add_text(_("1. Upload a KD file"), parent=parent)
        dpg.bind_item_theme(title, "theme.accent")
        dpg.add_button(
            label=_("Select input file (.KD)"),
            tag="spectra.upload",
            callback=self._choose_input,
            width=px(260),
            parent=parent,
        )
        dpg.add_text(_("No file selected"), tag="spectra.file", parent=parent)
        dpg.bind_item_theme("spectra.file", "theme.muted")
        dpg.add_spacer(height=px(12), parent=parent)
        title = dpg.add_text(_("2. Create Excel file"), parent=parent)
        dpg.bind_item_theme(title, "theme.accent")
        dpg.add_button(
            label=_("Generate Excel"),
            tag="spectra.export",
            callback=self._choose_output,
            enabled=False,
            width=px(260),
            parent=parent,
        )

    def _choose_input(self) -> None:
        self.open_file_dialog(
            title=_("Select a kinetic data file"),
            callback=lambda paths: self._load_input(paths[0]),
            filters={_("Kinetic data files"): ["*.KD", "*.kd"]},
            default_path=self.settings.get("famiglia_di_spettri/folder_input", "."),
        )

    def _load_input(self, path: Path) -> None:
        self.log(_("selected {path}").format(path=path))
        dpg.configure_item("spectra.upload", enabled=False)
        dpg.configure_item("spectra.export", enabled=False)
        dpg.set_value("spectra.file", _("Loading {name}...").format(name=path.name))

        def parsed(dataframe: pd.DataFrame) -> None:
            self.dataframe = dataframe
            self.input_path = path
            self.settings.set("famiglia_di_spettri/folder_input", str(path.parent))
            dpg.set_value(
                "spectra.file",
                _("{name} - {count} spectra").format(
                    name=path.name, count=len(dataframe.columns)
                ),
            )
            dpg.configure_item("spectra.upload", enabled=True)
            dpg.configure_item("spectra.export", enabled=True)
            self.log(_("loaded {name}").format(name=path.name))

        self.submit(
            lambda: parse_kd_file(path),
            parsed,
            lambda error: self._load_failed(error, path),
        )

    def _load_failed(self, error: Exception, path: Path) -> None:
        dpg.configure_item("spectra.upload", enabled=True)
        dpg.set_value(
            "spectra.file", _("Failed to load {name}").format(name=path.name)
        )
        self.log(_("ERROR: {error}").format(error=error))

    def _choose_output(self) -> None:
        if self.input_path is None or self.dataframe is None:
            return
        self.save_file_dialog(
            title=_("Save Excel file"),
            callback=self._export,
            default_path=self.settings.get("famiglia_di_spettri/folder_output", "."),
            default_filename=f"{datetime.now():%Y-%m-%d %H-%M-%S} spectrexcel.xlsx",
        )

    def _export(self, output_path: Path) -> None:
        if self.input_path is None or self.dataframe is None:
            return
        input_path = self.input_path
        dataframe = self.dataframe
        self.settings.set("famiglia_di_spettri/folder_output", str(output_path.parent))
        dpg.configure_item("spectra.export", enabled=False)
        self.log(_("generating excel file..."))
        self.submit(
            lambda: export_spectrum_family(dataframe, input_path, output_path),
            lambda _result: self._export_finished(),
            self._export_failed,
        )

    def _export_finished(self) -> None:
        dpg.configure_item("spectra.export", enabled=True)
        self.log(_("excel file saved successfully"))

    def _export_failed(self, error: Exception) -> None:
        dpg.configure_item("spectra.export", enabled=True)
        self.log(_("ERROR: {error}").format(error=error))
