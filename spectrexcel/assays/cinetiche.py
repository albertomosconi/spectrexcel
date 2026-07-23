from datetime import datetime
from pathlib import Path

import dearpygui.dearpygui as dpg
import pandas as pd
from natsort import natsorted
from xlsxwriter import Workbook, worksheet

from spectrexcel.i18n import _

from .parsing import WAVELENGTH_MAX, WAVELENGTH_MIN, parse_kd_file
from .view import AssayView, WorkflowControls


def export_kinetics(
    datasets: list[tuple[str, pd.DataFrame]],
    output_path: Path,
    reading_wavelength: int,
    correction_wavelength: int,
) -> None:
    if not datasets:
        raise ValueError(_("no kinetic data loaded"))

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        workbook: Workbook = writer.book
        sheet: worksheet.Worksheet = workbook.add_worksheet("data")
        sheet.write(0, 0, "tracce")
        sheet.write(1, 0, "Time (s)")
        sheet.write(
            0,
            4 + len(datasets),
            f"correction wavelength: {correction_wavelength}nm",
        )
        times = datasets[0][1].columns.values.astype(float)
        times = times - times[0]
        for row, value in enumerate(times, start=2):
            sheet.write(row, 0, float(value))

        chart = workbook.add_chart({"type": "scatter", "subtype": "smooth"})
        chart.set_title(
            {
                "name": "trends",
                "name_font": {"color": "gray", "size": 14, "bold": False},
            }
        )

        absorbance_max = 0.0
        for index, (filename, spectra) in enumerate(datasets):
            if reading_wavelength not in spectra.index:
                raise ValueError(
                    _("reading wavelength {wl}nm is unavailable").format(
                        wl=reading_wavelength
                    )
                )
            if correction_wavelength not in spectra.index:
                raise ValueError(
                    _("correction wavelength {wl}nm is unavailable").format(
                        wl=correction_wavelength
                    )
                )
            final = spectra.loc[reading_wavelength] - spectra.loc[correction_wavelength]
            absorbance_max = max(absorbance_max, float(final.max()))
            final.to_excel(
                writer,
                sheet_name="data",
                index=False,
                header=False,
                startrow=2,
                startcol=1 + index,
            )
            sheet.write(1, 1 + index, filename)
            chart.add_series(
                {
                    "categories": ["data", 2, 0, len(final) + 1, 0],
                    "values": ["data", 2, 1 + index, len(final) + 1, 1 + index],
                    "line": {"width": 1.25},
                    "name": ["data", 1, 1 + index],
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
                "max": float(times[-1]),
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
                "min": 0,
                "max": absorbance_max,
                "major_tick_mark": "none",
                "minor_tick_mark": "none",
            }
        )
        chart.set_size({"x_scale": 1.5, "y_scale": 1.5})
        chart.set_legend(
            {"position": "bottom", "font": {"color": "gray", "size": 9}}
        )
        chart.set_style(5)
        sheet.insert_chart(4, 4 + len(datasets), chart=chart)


class Cinetiche(AssayView):
    workflow_controls = WorkflowControls(
        upload="kinetics.upload",
        export="kinetics.export",
        status="kinetics.files",
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
        dpg.add_button(
            label=_("Generate Excel"),
            tag="kinetics.export",
            callback=self._choose_output,
            enabled=False,
            width=px(260),
            parent=parent,
        )

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
                dataframe = parse_kd_file(path)
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
        position = (
            max(0, (dpg.get_viewport_client_width() - width) // 2),
            max(0, (dpg.get_viewport_client_height() - height) // 2),
        )
        with dpg.window(
            label=_("Reorder kinetic files"),
            tag=tag,
            modal=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
            no_close=True,
            width=width,
            height=height,
            pos=position,
        ):
            dpg.add_text(_("Files and chart traces will use this order."))
            with dpg.child_window(height=list_height, border=True):
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
            dpg.add_button(
                label=_("Close"),
                callback=lambda: dpg.delete_item(tag),
                width=px(90),
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
        self.settings.set("cinetiche/folder_output", str(output_path.parent))
        self.settings.set("cinetiche/wl_read", reading)
        self.settings.set("cinetiche/wl_corr", correction)
        self.submit_export(
            lambda: export_kinetics(datasets, output_path, reading, correction)
        )
