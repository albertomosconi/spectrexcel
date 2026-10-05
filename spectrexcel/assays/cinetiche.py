from datetime import datetime
from pathlib import Path

import dearpygui.dearpygui as dpg
import pandas as pd
from natsort import natsorted
from xlsxwriter import Workbook, worksheet

from spectrexcel.dialogs import DialogAction, dialog_window
from spectrexcel.i18n import _

from .export_info import SourceInfo, parse_with_source, write_info_sheet
from .parsing import WAVELENGTH_MAX, WAVELENGTH_MIN, parse_kd_file
from .view import AssayView, ChartSeries, ChartSpec, WorkflowControls


def kinetics_chart_spec(
    datasets: list[tuple[str, pd.DataFrame]],
    reading_wavelength: int,
    correction_wavelength: int | None,
) -> ChartSpec:
    if not datasets:
        raise ValueError(_("no kinetic data loaded"))
    series = []
    absorbance_min, absorbance_max = 0.0, 0.0
    for filename, spectra in datasets:
        if spectra.empty:
            raise ValueError(_("no kinetic data loaded"))
        if reading_wavelength not in spectra.index:
            raise ValueError(
                _("reading wavelength {wl}nm is unavailable").format(wl=reading_wavelength)
            )
        if correction_wavelength is not None and correction_wavelength not in spectra.index:
            raise ValueError(
                _("correction wavelength {wl}nm is unavailable").format(
                    wl=correction_wavelength
                )
            )
        relative_times = spectra.columns.values.astype(float)
        relative_times = relative_times - relative_times[0]
        final = spectra.loc[reading_wavelength]
        if correction_wavelength is not None:
            final = final - spectra.loc[correction_wavelength]
        absorbance_min = min(absorbance_min, float(final.min()))
        absorbance_max = max(absorbance_max, float(final.max()))
        series.append(
            ChartSeries(
                name=filename,
                x=[float(value) for value in relative_times],
                y=[float(value) for value in final.values],
            )
        )
    if absorbance_min == absorbance_max:
        absorbance_max = absorbance_min + 1.0
    return ChartSpec(
        x_label="Time (s)",
        y_label=f"Abs{reading_wavelength} (AU)",
        x_limits=(0.0, max(max(trace.x) for trace in series)),
        y_limits=(absorbance_min, absorbance_max),
        series=tuple(series),
        title="trends",
        legend=True,
    )


def export_kinetics(
    datasets: list[tuple[str, pd.DataFrame]],
    output_path: Path,
    reading_wavelength: int,
    correction_wavelength: int,
    *,
    info_sources: tuple[SourceInfo, ...] | None = None,
) -> None:
    spec = kinetics_chart_spec(datasets, reading_wavelength, correction_wavelength)
    raw_spec = kinetics_chart_spec(datasets, reading_wavelength, None)

    def write_sheet(writer, sheet_name, spec):
        # Share time cells only for identical grids. Each other trace keeps its
        # exact timestamps, including acquisition jitter and different lengths.
        shared_times = all(trace.x == spec.series[0].x for trace in spec.series)
        data_columns = len(spec.series) + 1 if shared_times else 2 * len(spec.series)
        chart_column = data_columns + 3
        workbook: Workbook = writer.book
        sheet: worksheet.Worksheet = workbook.add_worksheet(sheet_name)
        sheet.write(0, 0, "tracce")
        if sheet_name == "data":
            sheet.write(
                0,
                chart_column,
                f"correction wavelength: {correction_wavelength}nm",
            )
        chart = workbook.add_chart({"type": "scatter", "subtype": "smooth"})
        chart.set_title(
            {
                "name": "trends",
                "name_font": {"color": "gray", "size": 14, "bold": False},
            }
        )

        for index, series in enumerate(spec.series):
            time_column = 0 if shared_times else 2 * index
            value_column = 1 + index if shared_times else time_column + 1
            if not shared_times or index == 0:
                sheet.write(1, time_column, "Time (s)")
                sheet.write_column(2, time_column, series.x)
            pd.Series(series.y).to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
                header=False,
                startrow=2,
                startcol=value_column,
            )
            sheet.write(1, value_column, series.name)
            chart.add_series(
                {
                    "categories": [sheet_name, 2, time_column, len(series.x) + 1, time_column],
                    "values": [sheet_name, 2, value_column, len(series.y) + 1, value_column],
                    "line": {"width": 1.25},
                    "name": [sheet_name, 1, value_column],
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
                "max": spec.x_limits[1],
                "major_tick_mark": "none",
                "minor_tick_mark": "none",
            }
        )
        chart.set_y_axis(
            {
                "name": f"Abs{reading_wavelength} (AU)",
                "name_font": {"bold": False, "color": "gray"},
                "num_font": {"color": "gray"},
                "num_format": "#,##0.00",
                "line": {"color": "gray"},
                "major_gridlines": {"visible": False},
                "interval_unit": 0.05,
                "min": spec.y_limits[0],
                "max": spec.y_limits[1],
                "major_tick_mark": "none",
                "minor_tick_mark": "none",
            }
        )
        chart.set_size({"x_scale": 1.5, "y_scale": 1.5})
        chart.set_legend(
            {"position": "bottom", "font": {"color": "gray", "size": 9}}
        )
        chart.set_style(5)
        sheet.insert_chart(4, chart_column, chart=chart)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        workbook: Workbook = writer.book
        write_sheet(writer, "data", spec)
        write_sheet(writer, "raw", raw_spec)
        if info_sources is not None:
            write_info_sheet(
                workbook, "kinetics", info_sources,
                {
                    "Reading wavelength (nm)": reading_wavelength,
                    "Correction wavelength (nm)": correction_wavelength,
                },
                [
                    "Subtract correction-wavelength absorbance from reading-wavelength absorbance.",
                    "Shift each trace's timestamps so its first measurement is at zero seconds.",
                    "Keep original acquisition intervals; export traces in the listed source order.",
                ],
            )


class Cinetiche(AssayView):
    workflow_controls = WorkflowControls(
        upload="kinetics.upload",
        export="kinetics.export",
        status="kinetics.files",
        preview="kinetics.preview",
        load_extras=("kinetics.reorder",),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datasets: list[tuple[str, pd.DataFrame]] = []

    def build(self, parent: str) -> None:
        px = self.display_scale.pixels
        title = dpg.add_text(_("1. Upload KD files"), parent=parent)
        dpg.bind_item_theme(title, "theme.accent")
        with dpg.group(horizontal=True, parent=parent):
            dpg.add_button(
                label=_("Select input files (.KD)"),
                tag="kinetics.upload",
                callback=self._choose_inputs,
                width=px(260),
            )
            dpg.add_button(
                label=_("Reorder files"),
                tag="kinetics.reorder",
                callback=self._show_reorder,
                enabled=False,
                width=px(150),
            )
        dpg.add_text(_("No files selected"), tag="kinetics.files", parent=parent)
        dpg.bind_item_theme("kinetics.files", "theme.muted")
        dpg.add_spacer(height=px(6), parent=parent)
        title = dpg.add_text(_("2. Configure parameters"), parent=parent)
        dpg.bind_item_theme(title, "theme.accent")
        with dpg.group(horizontal=True, parent=parent):
            with dpg.group():
                dpg.add_text(_("Reading wavelength (nm)"))
                dpg.add_input_int(
                    tag="kinetics.reading",
                    default_value=self.settings.get("cinetiche/wl_read", 300),
                    min_value=WAVELENGTH_MIN,
                    max_value=WAVELENGTH_MAX,
                    min_clamped=True,
                    max_clamped=True,
                    width=px(210),
                )
            with dpg.group():
                dpg.add_text(_("Correction wavelength (nm)"))
                dpg.add_input_int(
                    tag="kinetics.correction",
                    default_value=self.settings.get("cinetiche/wl_corr", 800),
                    min_value=WAVELENGTH_MIN,
                    max_value=WAVELENGTH_MAX,
                    min_clamped=True,
                    max_clamped=True,
                    width=px(210),
                )
        dpg.add_spacer(height=px(6), parent=parent)
        title = dpg.add_text(_("3. Create Excel file"), parent=parent)
        dpg.bind_item_theme(title, "theme.accent")
        with dpg.group(horizontal=True, parent=parent):
            dpg.add_button(
                label=_("Generate Excel"),
                tag="kinetics.export",
                callback=self._choose_output,
                enabled=False,
                width=px(260),
            )
            dpg.add_button(
                label=_("Preview chart"),
                tag="kinetics.preview",
                callback=self._show_preview,
                enabled=False,
                width=px(260),
            )
        self.add_info_checkbox(parent)

    def _choose_inputs(self) -> None:
        self.open_file_dialog(
            title=_("Select kinetic data files"),
            callback=self._load_inputs,
            filters={_("Kinetic data files"): ["*.KD", "*.kd"]},
            default_path=self.settings.get("cinetiche/folder_input", "."),
            multiple=True,
        )

    def _load_inputs(self, paths: list[Path]) -> None:
        self.log(_("selected {count} files").format(count=len(paths)))

        def parse() -> list[tuple[str, pd.DataFrame]]:
            datasets = []
            for path in paths:
                dataframe = parse_with_source(path, parse_kd_file)
                datasets.append((path.stem, dataframe))
            return datasets

        def loaded(datasets: list[tuple[str, pd.DataFrame]]) -> None:
            self.datasets = natsorted(datasets, key=lambda dataset: dataset[0])
            self.settings.set("cinetiche/folder_input", str(paths[0].parent))
            dpg.set_value(
                "kinetics.files",
                _("{count} files ready").format(count=len(datasets)),
            )
            dpg.configure_item("kinetics.reorder", enabled=len(datasets) > 1)
            for path in paths:
                self.log(_("loaded {name}").format(name=path.name))

        self.submit_load(
            parse,
            loaded,
            loading_text=_("Loading {count} files...").format(count=len(paths)),
            failure_text=_("Failed to load files"),
        )

    def _show_reorder(self) -> None:
        if len(self.datasets) < 2:
            return

        px = self.display_scale.pixels
        tag = "kinetics.reorder.modal"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        width = px(560)
        list_height = px(min(350, 34 * len(self.datasets)))
        height = list_height + px(130)
        with dialog_window(
            label=_("Reorder kinetic files"),
            tag=tag,
            width=width,
            height=height,
            scale=self.display_scale,
            actions=(DialogAction(_("Close"), lambda: dpg.delete_item(tag)),),
        ):
            dpg.add_text(_("Files and chart traces will use this order."))
            with dpg.child_window(height=-1, width=-1, border=True):
                for index, (filename, _dataframe) in enumerate(self.datasets):
                    with dpg.group(horizontal=True):
                        dpg.add_button(
                            label=_("Up"),
                            enabled=index > 0,
                            user_data=(index, -1),
                            callback=self._move_dataset,
                            width=px(60),
                        )
                        dpg.add_button(
                            label=_("Down"),
                            enabled=index < len(self.datasets) - 1,
                            user_data=(index, 1),
                            callback=self._move_dataset,
                            width=px(60),
                        )
                        dpg.add_text(
                            filename,
                            tag=f"kinetics.reorder.filename.{index}",
                            wrap=px(360),
                        )

    def _move_dataset(self, _sender, _app_data, move: tuple[int, int]) -> None:
        index, offset = move
        destination = index + offset
        if not 0 <= destination < len(self.datasets):
            return
        self.datasets[index], self.datasets[destination] = (
            self.datasets[destination],
            self.datasets[index],
        )
        for row, (filename, _dataframe) in enumerate(self.datasets):
            dpg.set_value(f"kinetics.reorder.filename.{row}", filename)

    def _show_preview(self) -> None:
        if not self.datasets:
            return
        reading = dpg.get_value("kinetics.reading")
        correction = dpg.get_value("kinetics.correction")
        try:
            spec = kinetics_chart_spec(self.datasets, reading, correction)
        except ValueError as error:
            self.log(_("ERROR: {error}").format(error=error))
            return
        self.show_chart_preview(spec)

    def _choose_output(self) -> None:
        if not self.datasets:
            return
        self.save_file_dialog(
            title=_("Save Excel file"),
            callback=self._export,
            default_path=self.settings.get("cinetiche/folder_output", "."),
            default_filename=f"{datetime.now():%Y-%m-%d %H-%M-%S} spectrexcel.xlsx",
        )

    def _export(self, output_path: Path) -> None:
        reading = dpg.get_value("kinetics.reading")
        correction = dpg.get_value("kinetics.correction")
        datasets = list(self.datasets)
        info_sources = (
            tuple(frame.attrs["source_info"] for name, frame in datasets)
            if dpg.get_value("kinetics.info") else None
        )
        self.settings.set("cinetiche/folder_output", str(output_path.parent))
        self.settings.set("cinetiche/wl_read", reading)
        self.settings.set("cinetiche/wl_corr", correction)
        self.submit_export(
            lambda: export_kinetics(
                datasets, output_path, reading, correction, info_sources=info_sources
            )
        )
