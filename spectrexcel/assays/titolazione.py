from pathlib import Path
from collections.abc import Callable
from typing import cast

import dearpygui.dearpygui as dpg
import pandas as pd
from xlsxwriter import Workbook, worksheet
from xlsxwriter.chart_scatter import ChartScatter

from spectrexcel.i18n import _

from .export_info import SourceInfo, parse_with_source, write_info_sheet
from .parsing import WAVELENGTH_MAX, WAVELENGTH_MIN, parse_sd_file, parse_txt_file
from .view import AssayView, ChartSeries, ChartSpec, WorkflowControls


def clean_duplicate_spectra(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:

    if len(df) < 2 or len(df) % 2 != 0:
        return df, False

    halfway_row = int(len(df) / 2)
    df_data = df.drop("#Sample", axis=1)
    df_1st_half = df_data.head(halfway_row).reset_index(drop=True)
    df_2nd_half = df_data.tail(halfway_row).reset_index(drop=True)

    if df_1st_half.equals(df_2nd_half):
        df = df.head(halfway_row)
        return df, True

    return df, False


def prepare_binding_spectra(
    dataframe: pd.DataFrame, correction_wavelength: int | None = None
) -> pd.DataFrame:
    dataframe = dataframe.drop(columns=["Std.Dev."], errors="ignore")
    if correction_wavelength is None:
        return dataframe
    wavelengths = dataframe.columns[1:]
    column = next(
        (value for value in wavelengths if float(value) == correction_wavelength),
        None,
    )
    if column is None:
        raise ValueError(
            _("correction wavelength {wl}nm is unavailable").format(
                wl=correction_wavelength
            )
        )
    corrected = dataframe.copy()
    corrected[wavelengths] = dataframe[wavelengths].sub(dataframe[column], axis=0)
    return corrected


def export_binding(
    dataframe: pd.DataFrame,
    output_path: Path,
    x_axis_min: int,
    x_axis_max: int,
    y_axis_min: float,
    y_axis_max: float,
    correction_wavelength: int | None = None,
    *,
    info_sources: tuple[SourceInfo, ...] | None = None,
    duplicates_removed: bool = False,
) -> None:
    if x_axis_min >= x_axis_max:
        raise ValueError(_("X-axis minimum must be lower than its maximum"))
    if y_axis_min >= y_axis_max:
        raise ValueError(_("Y-axis minimum must be lower than its maximum"))

    removed_std_dev = "Std.Dev." in dataframe.columns
    raw_dataframe = prepare_binding_spectra(dataframe)
    dataframe = prepare_binding_spectra(dataframe, correction_wavelength)

    def write_sheet(writer, sheet_name, dataframe, y_min, y_max):
        dataframe.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=1)
        workbook: Workbook = writer.book
        sheet: worksheet.Worksheet = writer.sheets[sheet_name]
        sheet.write(0, 0, dataframe.columns[0])
        for column, value in enumerate(dataframe.columns[1:].values, start=1):
            sheet.write(0, column, int(value))

        chart = cast(ChartScatter, workbook.add_chart({"type": "scatter", "subtype": "smooth"}))
        for row in range(len(dataframe)):
            chart.add_series(
                {
                    "categories": [sheet_name, 0, 1, 0, len(dataframe.columns)],
                    "values": [sheet_name, row + 1, 1, row + 1, len(dataframe.columns)],
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
                "min": y_min,
                "max": y_max,
                "major_tick_mark": "none",
                "minor_tick_mark": "none",
            }
        )
        chart.set_size({"x_scale": 1.5, "y_scale": 1.5})
        chart.set_legend({"position": "none"})
        chart.set_style(5)
        sheet.insert_chart(len(dataframe) + 2, 1, chart=chart)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        workbook: Workbook = writer.book
        write_sheet(writer, "data", dataframe, y_axis_min, y_axis_max)
        if correction_wavelength is not None:
            # Let Excel scale the raw chart independently of corrected-data limits.
            write_sheet(writer, "raw", raw_dataframe, None, None)
        if info_sources is not None:
            steps = []
            if duplicates_removed:
                steps.append("Remove identical repeated half of spectra.")
            if removed_std_dev:
                steps.append("Remove standard-deviation column.")
            if correction_wavelength is not None:
                steps.append("Subtract each spectrum's absorbance at the correction wavelength.")
            steps.append("Plot all exported spectra.")
            write_info_sheet(
                workbook, "binding / titration", info_sources,
                {
                    "X-axis minimum (nm)": x_axis_min,
                    "X-axis maximum (nm)": x_axis_max,
                    "Y-axis minimum (AU)": y_axis_min,
                    "Y-axis maximum (AU)": y_axis_max,
                    "Correction wavelength (nm)": correction_wavelength if correction_wavelength is not None else "Disabled",
                    "Duplicate spectra removed": duplicates_removed,
                },
                steps,
            )


def binding_chart_spec(
    dataframe: pd.DataFrame,
    x_min: int,
    x_max: int,
    y_min: float,
    y_max: float,
    correction_wavelength: int | None,
) -> ChartSpec:
    if x_min >= x_max or y_min >= y_max:
        raise ValueError(_("axis minimum must be lower than its maximum"))
    dataframe = prepare_binding_spectra(dataframe, correction_wavelength)
    wavelengths = [float(value) for value in dataframe.columns[1:].values]
    return ChartSpec(
        x_label="λ (nm)",
        y_label="Abs (AU)",
        x_limits=(float(x_min), float(x_max)),
        y_limits=(float(y_min), float(y_max)),
        series=tuple(
            ChartSeries(
                name=str(row[0]),
                x=wavelengths,
                y=[float(value) for value in row[1:]],
            )
            for row in dataframe.itertuples(index=False)
        ),
    )


class BindingTitolazione(AssayView):
    workflow_controls = WorkflowControls(
        upload="binding.upload",
        export="binding.export",
        status="binding.file",
        preview="binding.preview",
        export_extras=("binding.upload",),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dataframe: pd.DataFrame | None = None
        self.input_path: Path | None = None
        self.duplicates_removed = False

    def build(self, parent: str | int) -> None:
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
        with dpg.group(horizontal=True, parent=parent) as axes_row:
            with dpg.group():
                dpg.add_text(_("X-axis minimum (nm)"))
                dpg.add_input_int(
                    tag="binding.x_min",
                    callback=self.request_preview,
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
                    callback=self.request_preview,
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
                    callback=self.request_preview,
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
                    callback=self.request_preview,
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
        correction_enabled = self.settings.get("titolazione/correction_enabled", False)
        with dpg.group(horizontal=True, parent=parent) as correction_row:
            dpg.add_checkbox(
                label=_("Enable wavelength correction"),
                tag="binding.correction_enabled",
                default_value=correction_enabled,
                callback=lambda sender, enabled: self.set_correction_enabled(
                    "binding.correction", enabled
                ),
            )
            dpg.add_input_int(
                label=_("Correction wavelength (nm)"),
                tag="binding.correction",
                callback=self.request_preview,
                default_value=self.settings.get("titolazione/wl_corr", 800),
                min_value=WAVELENGTH_MIN,
                max_value=WAVELENGTH_MAX,
                min_clamped=True,
                max_clamped=True,
                width=px(210),
                show=correction_enabled,
            )
        dpg.add_spacer(height=px(6), parent=parent)
        title = dpg.add_text(_("3. Create Excel file"), parent=parent)
        dpg.bind_item_theme(title, "theme.accent")
        with dpg.group(horizontal=True, parent=parent):
            dpg.add_button(
                label=_("Generate Excel"),
                tag="binding.export",
                callback=self._choose_output,
                enabled=False,
                width=px(260),
            )
            dpg.add_button(
                label=_("Preview chart"),
                tag="binding.preview",
                callback=self._show_preview,
                enabled=False,
                width=px(260),
            )
        self.add_info_checkbox(parent)
        self.register_layout_row(axes_row)
        self.register_layout_row(correction_row)
        for tag in ("binding.x_min", "binding.x_max", "binding.y_min", "binding.y_max"):
            self.register_layout_field(tag, 180)
        self.register_layout_field("binding.correction", 210, _("Correction wavelength (nm)"))
        self.register_layout_field("binding.upload", 260)
        self.register_layout_field("binding.export", 260)

    def _choose_input(self) -> None:
        self.open_file_dialog(
            title=_("Select a spectra file"),
            callback=lambda paths: self._load_input(paths[0]),
            filters={_("Spectra files"): ["*.txt", "*.TXT", "*.SD", "*.sd"]},
            default_path=self.settings.get("main/folder_input", "."),
        )

    def _load_input(self, path: Path) -> None:
        self.log(_("selected {path}").format(path=path))

        def parse() -> tuple[pd.DataFrame, bool]:
            if path.suffix.upper() == ".SD":
                dataframe = parse_with_source(path, parse_sd_file)
            elif path.suffix.upper() == ".TXT":
                dataframe = parse_with_source(path, parse_txt_file)
            else:
                raise ValueError(_("unknown input format"))
            return clean_duplicate_spectra(dataframe)

        def loaded(result: tuple[pd.DataFrame, bool]) -> None:
            self.dataframe, did_clean = result
            self.duplicates_removed = did_clean
            self.input_path = path
            self.settings.set("main/folder_input", str(path.parent))
            dpg.set_value(
                "binding.file",
                _("{name} - {count} signals").format(
                    name=path.name, count=len(self.dataframe)
                ),
            )
            if did_clean:
                self.log(_("deleted duplicate spectra"))
            self.log(
                _("the file contains {count} signals").format(
                    count=len(self.dataframe)
                )
            )

        self.submit_load(
            parse,
            loaded,
            loading_text=_("Loading {name}...").format(name=path.name),
            failure_text=_("Failed to load {name}").format(name=path.name),
        )

    def preview_tab_labels(self) -> list[str]:
        return [_("Spectra")]

    def preview_task(self, tab: int = 0) -> Callable[[], ChartSpec] | None:
        if self.dataframe is None:
            return None
        dataframe = self.dataframe
        x_min = dpg.get_value("binding.x_min")
        x_max = dpg.get_value("binding.x_max")
        y_min = dpg.get_value("binding.y_min")
        y_max = dpg.get_value("binding.y_max")
        correction = (
            dpg.get_value("binding.correction")
            if dpg.get_value("binding.correction_enabled") else None
        )
        return lambda: binding_chart_spec(
            dataframe, x_min, x_max, y_min, y_max, correction
        )

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
        correction_enabled = dpg.get_value("binding.correction_enabled")
        correction = dpg.get_value("binding.correction")
        self.settings.set("titolazione/correction_enabled", correction_enabled)
        self.settings.set("titolazione/wl_corr", correction)
        dataframe = self.dataframe
        info_sources = (dataframe.attrs["source_info"],) if dpg.get_value("binding.info") else None
        duplicates_removed = self.duplicates_removed
        self.submit_export(
            lambda: export_binding(
                dataframe,
                output_path,
                x_min,
                x_max,
                y_min,
                y_max,
                correction if correction_enabled else None,
                info_sources=info_sources,
                duplicates_removed=duplicates_removed,
            )
        )
