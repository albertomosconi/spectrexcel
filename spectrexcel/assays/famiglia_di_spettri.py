from datetime import datetime
from pathlib import Path
from typing import Callable

import dearpygui.dearpygui as dpg
import pandas as pd
from xlsxwriter import Workbook, worksheet

from spectrexcel.i18n import _

from .export_info import SourceInfo, parse_with_source, write_info_sheet
from .parsing import WAVELENGTH_MAX, WAVELENGTH_MIN, parse_kd_file
from .view import AssayView, ChartSeries, ChartSpec, WorkflowControls


def prepare_spectrum_family(
    dataframe: pd.DataFrame, correction_wavelength: int | None = None
) -> pd.DataFrame:
    if correction_wavelength is None:
        return dataframe
    if correction_wavelength not in dataframe.index:
        raise ValueError(
            _("correction wavelength {wl}nm is unavailable").format(
                wl=correction_wavelength
            )
        )
    return dataframe.sub(dataframe.loc[correction_wavelength], axis=1)


def spectrum_family_y_limits(
    dataframe: pd.DataFrame, corrected: bool
) -> tuple[float, float]:
    minimum = min(0.0, float(dataframe.min().min())) if corrected else 0.0
    maximum = float(dataframe.max().max())
    if corrected and minimum == maximum:
        maximum = minimum + 1.0
    return minimum, maximum


def export_spectrum_family(
    dataframe: pd.DataFrame, input_path: Path, output_path: Path,
    correction_wavelength: int | None = None,
    *,
    info_sources: tuple[SourceInfo, ...] | None = None,
) -> None:
    raw_dataframe = dataframe
    dataframe = prepare_spectrum_family(dataframe, correction_wavelength)
    y_min, y_max = spectrum_family_y_limits(dataframe, correction_wavelength is not None)

    def write_sheet(writer, sheet_name, dataframe, y_min, y_max):
        workbook: Workbook = writer.book
        sheet: worksheet.Worksheet = workbook.add_worksheet(sheet_name)
        chart = workbook.add_chart({"type": "scatter", "subtype": "smooth"})
        dataframe.to_excel(writer, sheet_name=sheet_name, index=True, header=True)

        for column in range(0, len(dataframe.columns), 2):
            chart.add_series(
                {
                    "categories": [sheet_name, 1, 0, len(dataframe), 0],
                    "values": [sheet_name, 1, 1 + column, len(dataframe), 1 + column],
                    "line": {"width": 1},
                    "name": [sheet_name, 0, 1 + column],
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
                "min": y_min,
                "max": y_max,
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

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        workbook: Workbook = writer.book
        write_sheet(writer, "data", dataframe, y_min, y_max)
        if correction_wavelength is not None:
            raw_y_min, raw_y_max = spectrum_family_y_limits(raw_dataframe, True)
            write_sheet(writer, "raw", raw_dataframe, raw_y_min, raw_y_max)
        if info_sources is not None:
            write_info_sheet(
                workbook, "spectrum family", info_sources,
                {
                    "Correction wavelength (nm)": correction_wavelength if correction_wavelength is not None else "Disabled",
                    "Chart spectrum stride": 2,
                    "X-axis minimum (nm)": WAVELENGTH_MIN,
                    "X-axis maximum (nm)": WAVELENGTH_MAX,
                    "Y-axis minimum (AU)": y_min,
                    "Y-axis maximum (AU)": y_max,
                },
                (["Subtract each spectrum's absorbance at the correction wavelength."]
                 if correction_wavelength is not None else [])
                + ["Export all spectra; plot every second spectrum, starting with the first."],
            )


def spectrum_family_chart_spec(
    dataframe: pd.DataFrame, input_path: Path, correction_wavelength: int | None
) -> ChartSpec:
    dataframe = prepare_spectrum_family(dataframe, correction_wavelength)
    wavelengths = [float(value) for value in dataframe.index.values]
    return ChartSpec(
        x_label="λ (nm)",
        y_label="Abs (AU)",
        x_limits=(float(WAVELENGTH_MIN), float(WAVELENGTH_MAX)),
        y_limits=spectrum_family_y_limits(dataframe, correction_wavelength is not None),
        series=tuple(
            ChartSeries(
                name=str(dataframe.columns[column]),
                x=wavelengths,
                y=[float(value) for value in dataframe.iloc[:, column].values],
            )
            for column in range(0, len(dataframe.columns), 2)
        ),
        title=input_path.stem,
    )


class FamigliaDiSpettri(AssayView):
    workflow_controls = WorkflowControls(
        upload="spectra.upload",
        export="spectra.export",
        status="spectra.file",
        preview="spectra.preview",
    )

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
        title = dpg.add_text(_("2. Configure parameters"), parent=parent)
        dpg.bind_item_theme(title, "theme.accent")
        correction_enabled = self.settings.get(
            "famiglia_di_spettri/correction_enabled", False
        )
        with dpg.group(horizontal=True, parent=parent) as correction_row:
            dpg.add_checkbox(
                label=_("Enable wavelength correction"),
                tag="spectra.correction_enabled",
                default_value=correction_enabled,
                callback=lambda sender, enabled: self.set_correction_enabled(
                    "spectra.correction", enabled
                ),
            )
            dpg.add_input_int(
                label=_("Correction wavelength (nm)"),
                tag="spectra.correction",
                callback=self.request_preview,
                default_value=self.settings.get("famiglia_di_spettri/wl_corr", 800),
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
                tag="spectra.export",
                callback=self._choose_output,
                enabled=False,
                width=px(260),
            )
            dpg.add_button(
                label=_("Preview chart"),
                tag="spectra.preview",
                callback=self._show_preview,
                enabled=False,
                width=px(260),
            )
        self.add_info_checkbox(parent)
        self.register_layout_row(correction_row)
        self.register_layout_field("spectra.correction", 210, _("Correction wavelength (nm)"))
        self.register_layout_field("spectra.upload", 260)
        self.register_layout_field("spectra.export", 260)

    def _choose_input(self) -> None:
        self.open_file_dialog(
            title=_("Select a kinetic data file"),
            callback=lambda paths: self._load_input(paths[0]),
            filters={_("Kinetic data files"): ["*.KD", "*.kd"]},
            default_path=self.settings.get("famiglia_di_spettri/folder_input", "."),
        )

    def _load_input(self, path: Path) -> None:
        self.log(_("selected {path}").format(path=path))

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
            self.log(_("loaded {name}").format(name=path.name))

        self.submit_load(
            lambda: parse_with_source(path, parse_kd_file),
            parsed,
            loading_text=_("Loading {name}...").format(name=path.name),
            failure_text=_("Failed to load {name}").format(name=path.name),
        )

    def preview_task(self) -> Callable[[], ChartSpec] | None:
        if self.input_path is None or self.dataframe is None:
            return None
        dataframe, input_path = self.dataframe, self.input_path
        correction = (
            dpg.get_value("spectra.correction")
            if dpg.get_value("spectra.correction_enabled") else None
        )
        return lambda: spectrum_family_chart_spec(
            dataframe, input_path, correction
        )

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
        info_sources = (dataframe.attrs["source_info"],) if dpg.get_value("spectra.info") else None
        self.settings.set("famiglia_di_spettri/folder_output", str(output_path.parent))
        correction_enabled = dpg.get_value("spectra.correction_enabled")
        correction = dpg.get_value("spectra.correction")
        self.settings.set("famiglia_di_spettri/correction_enabled", correction_enabled)
        self.settings.set("famiglia_di_spettri/wl_corr", correction)
        self.submit_export(
            lambda: export_spectrum_family(
                dataframe, input_path, output_path,
                correction if correction_enabled else None,
                info_sources=info_sources,
            ),
        )
