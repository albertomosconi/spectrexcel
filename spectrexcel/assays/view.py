from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import dearpygui.dearpygui as dpg

from spectrexcel.dpi import DisplayScale
from spectrexcel import native_dialogs
from spectrexcel.i18n import _
from spectrexcel.settings import Settings


@dataclass(frozen=True)
class WorkflowControls:
    upload: str
    export: str
    status: str
    preview: str | None = None
    load_extras: tuple[str, ...] = ()
    export_extras: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChartSeries:
    name: str
    x: list[float]
    y: list[float]


@dataclass(frozen=True)
class ChartSpec:
    x_label: str
    y_label: str
    x_limits: tuple[float, float]
    y_limits: tuple[float, float]
    series: tuple[ChartSeries, ...]
    title: str | None = None
    legend: bool = False


def green_shades(count: int) -> list[tuple[int, int, int, int]]:
    """Monochromatic green scale matching Excel chart style 5."""
    light = (197, 224, 180)
    dark = (56, 87, 35)
    if count <= 1:
        return [(112, 173, 71, 255)]
    return [
        (
            *(
                round(light[channel] + (dark[channel] - light[channel]) * step)
                for channel in range(3)
            ),
            255,
        )
        for step in (index / (count - 1) for index in range(count))
    ]


class AssayView:
    workflow_controls: WorkflowControls | None = None

    def __init__(
        self,
        log: Callable[[str | list[str]], None],
        submit: Callable[..., None],
        settings: Settings,
        display_scale: DisplayScale,
    ):
        self.log = log
        self._submit = submit
        self.settings = settings
        self.display_scale = display_scale
        self.active = True

    def dispose(self) -> None:
        self.active = False

    def submit(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        def if_active(callback: Callable[[Any], None]) -> Callable[[Any], None]:
            return lambda value: callback(value) if self.active else None

        self._submit(task, if_active(on_success), if_active(on_error))

    def _workflow(self) -> WorkflowControls:
        if self.workflow_controls is None:
            raise RuntimeError("Assay workflow controls are not configured")
        return self.workflow_controls

    def submit_load(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        *,
        loading_text: str,
        failure_text: str,
    ) -> None:
        controls = self._workflow()
        busy_controls = [controls.upload, controls.export, *controls.load_extras]
        if controls.preview is not None:
            busy_controls.append(controls.preview)
        for tag in busy_controls:
            dpg.configure_item(tag, enabled=False)
        dpg.set_value(controls.status, loading_text)

        def loaded(value: Any) -> None:
            on_success(value)
            dpg.configure_item(controls.upload, enabled=True)
            dpg.configure_item(controls.export, enabled=True)
            if controls.preview is not None:
                dpg.configure_item(controls.preview, enabled=True)

        def failed(error: Exception) -> None:
            dpg.configure_item(controls.upload, enabled=True)
            dpg.set_value(controls.status, failure_text)
            self.log(_("ERROR: {error}").format(error=error))

        self.submit(task, loaded, failed)

    def submit_export(self, task: Callable[[], Any]) -> None:
        controls = self._workflow()
        busy_controls = [controls.export, *controls.export_extras]
        if controls.preview is not None:
            busy_controls.append(controls.preview)
        for tag in busy_controls:
            dpg.configure_item(tag, enabled=False)
        self.log(_("generating excel file..."))

        def restore_controls() -> None:
            for tag in busy_controls:
                dpg.configure_item(tag, enabled=True)

        def finished(_result: Any) -> None:
            restore_controls()
            self.log(_("excel file saved successfully"))

        def failed(error: Exception) -> None:
            restore_controls()
            self.log(_("ERROR: {error}").format(error=error))

        self.submit(task, finished, failed)

    def open_file_dialog(
        self,
        *,
        title: str,
        callback: Callable[[list[Path]], None],
        filters: dict[str, list[str]],
        default_path: str,
        multiple: bool = False,
    ) -> None:
        try:
            selected = native_dialogs.open_files(title, default_path, filters, multiple)
        except Exception as error:
            self.log(
                _("ERROR: unable to open the system file picker: {error}").format(
                    error=error
                )
            )
            return
        paths = [Path(value) for value in selected if value]
        if paths:
            callback(paths)

    def save_file_dialog(
        self,
        *,
        title: str,
        callback: Callable[[Path], None],
        default_path: str,
        default_filename: str,
    ) -> None:
        try:
            selected = native_dialogs.save_file(
                title,
                default_path,
                default_filename,
                {_("Excel workbook"): ["*.xlsx"]},
            )
        except Exception as error:
            self.log(
                _("ERROR: unable to open the system file picker: {error}").format(
                    error=error
                )
            )
            return
        if not selected:
            return
        selected_path = Path(selected)
        path = (
            selected_path
            if selected_path.suffix.lower() == ".xlsx"
            else selected_path.with_suffix(".xlsx")
        )
        if path != selected_path and path.exists():
            self._confirm_overwrite(path, callback)
        else:
            callback(path)

    def _confirm_overwrite(
        self, path: Path, callback: Callable[[Path], None]
    ) -> None:
        px = self.display_scale.pixels
        tag = "save.overwrite"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        with dpg.window(
            label=_("Replace existing file?"),
            tag=tag,
            modal=True,
            no_close=True,
            width=px(430),
            height=px(145),
            pos=self.display_scale.position((185, 175)),
        ):
            dpg.add_text(
                _("{name} already exists. Replace it?").format(name=path.name),
                wrap=px(390),
            )
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label=_("Replace"),
                    width=px(100),
                    callback=lambda: (dpg.delete_item(tag), callback(path)),
                )
                dpg.add_button(
                    label=_("Cancel"),
                    width=px(100),
                    callback=lambda: dpg.delete_item(tag),
                )

    def show_chart_preview(self, spec: ChartSpec) -> None:
        px = self.display_scale.pixels
        tag = "chart.preview.modal"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        width, height = px(760), px(600)
        position = (
            max(0, (dpg.get_viewport_client_width() - width) // 2),
            max(0, (dpg.get_viewport_client_height() - height) // 2),
        )
        with dpg.window(
            label=_("Chart preview"),
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
            with dpg.plot(
                label=spec.title or "",
                no_title=spec.title is None,
                width=-1,
                height=height - px(115),
            ):
                if spec.legend:
                    dpg.add_plot_legend(
                        location=dpg.mvPlot_Location_South,
                        horizontal=True,
                        outside=True,
                    )
                x_axis = dpg.add_plot_axis(dpg.mvXAxis, label=spec.x_label)
                y_axis = dpg.add_plot_axis(dpg.mvYAxis, label=spec.y_label)
                shades = green_shades(len(spec.series))
                for index, series in enumerate(spec.series):
                    item = dpg.add_line_series(
                        series.x,
                        series.y,
                        label=series.name if spec.legend else f"##series{index}",
                        parent=y_axis,
                    )
                    with dpg.theme() as series_theme:
                        with dpg.theme_component(dpg.mvLineSeries):
                            dpg.add_theme_color(
                                dpg.mvPlotCol_Line,
                                shades[index],
                                category=dpg.mvThemeCat_Plots,
                            )
                    dpg.bind_item_theme(item, series_theme)
                dpg.set_axis_limits(x_axis, *spec.x_limits)
                dpg.set_axis_limits(y_axis, *spec.y_limits)
            dpg.add_button(
                label=_("Close"),
                width=px(90),
                callback=lambda: dpg.delete_item(tag),
            )
