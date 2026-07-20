from pathlib import Path

import dearpygui.dearpygui as dpg
import pandas as pd
from xlsxwriter import Workbook, worksheet

from spectrexcel.i18n import _

from .shared import AssayView, clean_duplicate_spectra, parse_sd_file, parse_txt_file


def export_binding(
    dataframe: pd.DataFrame,
    output_path: Path,
    x_axis_min: int,
    x_axis_max: int,
    y_axis_min: float,
    y_axis_max: float,
) -> None:
    if x_axis_min >= x_axis_max:
        raise ValueError(_("X-axis minimum must be lower than its maximum"))
    if y_axis_min >= y_axis_max:
        raise ValueError(_("Y-axis minimum must be lower than its maximum"))

    if "Std.Dev." in dataframe.columns:
        dataframe = dataframe.drop("Std.Dev.", axis=1)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        dataframe.to_excel(writer, sheet_name="data", index=False, header=False, startrow=1)
        workbook: Workbook = writer.book
        sheet: worksheet.Worksheet = writer.sheets["data"]
        sheet.write(0, 0, dataframe.columns[0])
        for column, value in enumerate(dataframe.columns[1:].values, start=1):
            sheet.write(0, column, int(value))

        chart = workbook.add_chart({"type": "scatter", "subtype": "smooth"})
        for row in range(len(dataframe)):
            chart.add_series(
                {
                    "categories": ["data", 0, 1, 0, len(dataframe.columns)],
                    "values": ["data", row + 1, 1, row + 1, len(dataframe.columns)],
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
                "min": x_axis_min,
                "max": x_axis_max,
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
                "min": y_axis_min,
                "max": y_axis_max,
                "major_tick_mark": "none",
                "minor_tick_mark": "none",
            }
        )
        chart.set_size({"x_scale": 1.5, "y_scale": 1.5})
        chart.set_legend({"position": "none"})
        chart.set_style(5)
        sheet.insert_chart(len(dataframe) + 2, 1, chart=chart)


class BindingTitolazione(AssayView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dataframe: pd.DataFrame | None = None
        self.input_path: Path | None = None

    def build(self, parent: str) -> None:
        px = self.display_scale.pixels
        title = dpg.add_text(_("1. Upload a TXT or SD file"), parent=parent)
        dpg.bind_item_theme(title, "theme.accent")
        dpg.add_button(
            label=_("Select input file (.txt, .SD)"),
            tag="binding.upload",
            callback=self._choose_input,
            width=px(260),
            parent=parent,
        )
        dpg.add_text(_("No file selected"), tag="binding.file", parent=parent)
        dpg.bind_item_theme("binding.file", "theme.muted")
        dpg.add_spacer(height=px(6), parent=parent)
        title = dpg.add_text(_("2. Configure axis ranges"), parent=parent)
        dpg.bind_item_theme(title, "theme.accent")
        with dpg.group(horizontal=True, parent=parent):
            with dpg.group():
                dpg.add_text(_("X-axis minimum (nm)"))
                dpg.add_input_int(
                    tag="binding.x_min",
                    default_value=self.settings.get("titolazione/x_axis_min", 200),
                    min_value=0,
                    max_value=1_000_000,
                    min_clamped=True,
                    max_clamped=True,
                    width=px(180),
                )
            with dpg.group():
                dpg.add_text(_("X-axis maximum (nm)"))
                dpg.add_input_int(
                    tag="binding.x_max",
                    default_value=self.settings.get("titolazione/x_axis_max", 800),
                    min_value=0,
                    max_value=1_000_000,
                    min_clamped=True,
                    max_clamped=True,
                    width=px(180),
                )
            with dpg.group():
                dpg.add_text(_("Y-axis minimum (AU)"))
                dpg.add_input_float(
                    tag="binding.y_min",
                    default_value=self.settings.get("titolazione/y_axis_min", 0.0),
                    min_value=-1_000_000.0,
                    max_value=1_000_000.0,
                    min_clamped=True,
                    max_clamped=True,
                    format="%.4f",
                    step=0.05,
                    width=px(180),
                )
            with dpg.group():
                dpg.add_text(_("Y-axis maximum (AU)"))
                dpg.add_input_float(
                    tag="binding.y_max",
                    default_value=self.settings.get("titolazione/y_axis_max", 0.5),
                    min_value=-1_000_000.0,
                    max_value=1_000_000.0,
                    min_clamped=True,
                    max_clamped=True,
                    format="%.4f",
                    step=0.05,
                    width=px(180),
                )
        dpg.add_spacer(height=px(6), parent=parent)
        title = dpg.add_text(_("3. Create Excel file"), parent=parent)
        dpg.bind_item_theme(title, "theme.accent")
        dpg.add_button(
            label=_("Generate Excel"),
            tag="binding.export",
            callback=self._choose_output,
            enabled=False,
            width=px(260),
            parent=parent,
        )

    def _choose_input(self) -> None:
        self.open_file_dialog(
            title=_("Select a spectra file"),
            callback=lambda paths: self._load_input(paths[0]),
            filters={_("Spectra files"): ["*.txt", "*.TXT", "*.SD", "*.sd"]},
            default_path=self.settings.get("main/folder_input", "."),
        )

    def _load_input(self, path: Path) -> None:
        self.log(_("selected {path}").format(path=path))
        dpg.configure_item("binding.upload", enabled=False)
        dpg.configure_item("binding.export", enabled=False)
        dpg.set_value("binding.file", _("Loading {name}...").format(name=path.name))

        def parse() -> tuple[pd.DataFrame, bool]:
            if path.suffix.upper() == ".SD":
                dataframe = parse_sd_file(path)
            elif path.suffix.upper() == ".TXT":
                dataframe = parse_txt_file(path)
            else:
                raise ValueError(_("unknown input format"))
            return clean_duplicate_spectra(dataframe)

        def loaded(result: tuple[pd.DataFrame, bool]) -> None:
            self.dataframe, did_clean = result
            self.input_path = path
            self.settings.set("main/folder_input", str(path.parent))
            dpg.set_value(
                "binding.file",
                _("{name} - {count} signals").format(
                    name=path.name, count=len(self.dataframe)
                ),
            )
            dpg.configure_item("binding.upload", enabled=True)
            dpg.configure_item("binding.export", enabled=True)
            if did_clean:
                self.log(_("deleted duplicate spectra"))
            self.log(
                _("the file contains {count} signals").format(
                    count=len(self.dataframe)
                )
            )

        self.submit(parse, loaded, lambda error: self._load_failed(error, path))

    def _load_failed(self, error: Exception, path: Path) -> None:
        dpg.configure_item("binding.upload", enabled=True)
        dpg.set_value(
            "binding.file", _("Failed to load {name}").format(name=path.name)
        )
        self.log(_("ERROR: {error}").format(error=error))

    def _choose_output(self) -> None:
        if self.input_path is None or self.dataframe is None:
            return
        self.save_file_dialog(
            title=_("Save Excel file"),
            callback=self._export,
            default_path=self.settings.get("main/folder_output", "."),
            default_filename=f"{self.input_path.stem}.xlsx",
        )

    def _export(self, output_path: Path) -> None:
        if self.dataframe is None:
            return
        x_min = dpg.get_value("binding.x_min")
        x_max = dpg.get_value("binding.x_max")
        y_min = dpg.get_value("binding.y_min")
        y_max = dpg.get_value("binding.y_max")
        if x_min >= x_max or y_min >= y_max:
            self.log(_("ERROR: axis minimum must be lower than its maximum"))
            return

        self.settings.set("main/folder_output", str(output_path.parent))
        self.settings.set("titolazione/x_axis_min", x_min)
        self.settings.set("titolazione/x_axis_max", x_max)
        self.settings.set("titolazione/y_axis_min", y_min)
        self.settings.set("titolazione/y_axis_max", y_max)
        dpg.configure_item("binding.export", enabled=False)
        dpg.configure_item("binding.upload", enabled=False)
        self.log(_("generating excel file..."))
        dataframe = self.dataframe
        self.submit(
            lambda: export_binding(dataframe, output_path, x_min, x_max, y_min, y_max),
            lambda _result: self._export_finished(),
            self._export_failed,
        )

    def _export_finished(self) -> None:
        dpg.configure_item("binding.export", enabled=True)
        dpg.configure_item("binding.upload", enabled=True)
        self.log(_("excel file saved successfully"))

    def _export_failed(self, error: Exception) -> None:
        dpg.configure_item("binding.export", enabled=True)
        dpg.configure_item("binding.upload", enabled=True)
        self.log(_("ERROR: {error}").format(error=error))
