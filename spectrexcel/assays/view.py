from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any

import dearpygui.dearpygui as dpg

from spectrexcel.dpi import DisplayScale
from spectrexcel.dialogs import DialogAction, dialog_window
from spectrexcel import native_dialogs
from spectrexcel.i18n import _
from spectrexcel.settings import Settings
from spectrexcel.charts import ChartRenderer, ChartSeries, ChartSpec, green_shades
from spectrexcel.layouts import AssayLayout, PARAMETERS_ONLY, PARAMETERS_PREVIEW, resolve_layout


@dataclass(frozen=True)
class WorkflowControls:
    upload: str
    export: str
    status: str
    preview: str | None = None
    load_extras: tuple[str, ...] = ()
    export_extras: tuple[str, ...] = ()


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
        self._modal_renderer: ChartRenderer | None = None
        self._embedded_renderer: ChartRenderer | None = None
        self.layout = PARAMETERS_ONLY
        self._assay_layout: AssayLayout | None = None
        self._layout_rows: list[str | int] = []
        self._layout_fields: list[tuple[str | int, int, str, str | int | None]] = []
        self._preview_message: str | int | None = None
        self._preview_generation = 0
        self._preview_dirty = False
        self._preview_running = False
        self._input_loading = False
        self._input_error: str | None = None

    def build(self, parent: str | int) -> None:
        raise NotImplementedError

    def mount(self, parent: str | int, layout: str) -> None:
        self._assay_layout = AssayLayout(parent, self.display_scale)
        self.build(self._assay_layout.parameters)
        self._preview_message = dpg.add_text("", parent=self._assay_layout.preview)
        self._embedded_renderer = ChartRenderer(self._assay_layout.preview)
        self.apply_layout(layout)

    def register_layout_row(self, tag: str | int) -> None:
        self._layout_rows.append(tag)

    def register_layout_field(self, tag: str | int, width: int, label: str = "") -> None:
        heading = None
        if label:
            heading = dpg.add_text(
                label, parent=dpg.get_item_parent(tag) or 0, before=tag, show=False,
            )
        self._layout_fields.append((tag, width, label, heading))

    def apply_layout(self, layout: str) -> None:
        self.close_chart_preview()
        self.layout = resolve_layout(layout)
        if self._assay_layout is None:
            return
        embedded = self.layout == PARAMETERS_PREVIEW
        self._assay_layout.apply(self.layout)
        for row in self._layout_rows:
            dpg.configure_item(row, horizontal=not embedded)
        for tag, width, label, heading in self._layout_fields:
            if heading is not None:
                dpg.configure_item(heading, show=embedded and dpg.get_item_configuration(tag)["show"])
                dpg.configure_item(tag, label="" if embedded else label)
        preview = self._workflow().preview
        if preview is not None:
            dpg.configure_item(preview, show=not embedded)
        self.maintain_layout()
        self.request_preview()

    def set_preview_message(self, text: str) -> None:
        if self._embedded_renderer is not None:
            self._embedded_renderer.clear()
        if self._preview_message is not None:
            dpg.set_value(self._preview_message, text)
            dpg.configure_item(self._preview_message, show=True)

    def request_preview(self, _sender: Any = None, _value: Any = None) -> None:
        self._preview_generation += 1
        self._preview_dirty = (
            self.active and self.layout == PARAMETERS_PREVIEW
            and self._embedded_renderer is not None
        )
        if not self._preview_dirty:
            return
        if self._input_loading:
            self.set_preview_message(_("Loading chart data..."))
        elif self._input_error is not None:
            self.set_preview_message(self._input_error)
        else:
            self.set_preview_message(_("Updating chart..."))

    def set_correction_enabled(self, tag: str, enabled: bool) -> None:
        dpg.configure_item(tag, show=enabled)
        self.maintain_layout()
        self.request_preview()

    def process_preview(self) -> None:
        if (
            not self.active or not self._preview_dirty or self._preview_running
            or self._input_loading or self._input_error is not None
        ):
            return
        self._preview_dirty = False
        task = self.preview_task()
        if task is None:
            self.set_preview_message(_("Select input files to preview the chart."))
            return
        generation = self._preview_generation
        self._preview_running = True

        def current() -> bool:
            return (
                generation == self._preview_generation and self.active
                and self.layout == PARAMETERS_PREVIEW
                and not self._input_loading and self._input_error is None
            )

        def failed(error: Exception) -> None:
            self._preview_running = False
            if current():
                self.set_preview_message(_("Unable to preview chart: {error}").format(error=error))

        def finished(spec: ChartSpec) -> None:
            self._preview_running = False
            if current() and self._embedded_renderer is not None:
                try:
                    if self._preview_message is not None:
                        dpg.configure_item(self._preview_message, show=False)
                    self._embedded_renderer.render(spec)
                except Exception as error:
                    failed(error)

        self.submit(task, finished, failed)

    def maintain_layout(self) -> None:
        if self._assay_layout is None:
            return
        self._assay_layout.maintain()
        embedded = self.layout == PARAMETERS_PREVIEW
        width = self._assay_layout.content_width
        for tag, logical_width, label, heading in self._layout_fields:
            field_width = self.display_scale.pixels(logical_width)
            dpg.configure_item(tag, width=min(field_width, width) if embedded else field_width)
            if heading is not None:
                dpg.configure_item(heading, show=embedded and dpg.get_item_configuration(tag)["show"])
        dpg.configure_item(self._workflow().status, wrap=width if embedded else -1)
        if self._preview_message is not None:
            dpg.configure_item(self._preview_message, wrap=width)

    def dispose(self) -> None:
        self.active = False
        self._preview_generation += 1
        self.close_chart_preview()
        if self._embedded_renderer is not None:
            self._embedded_renderer.dispose()
        if self._assay_layout is not None:
            self._assay_layout.dispose()

    def close_chart_preview(self) -> None:
        if self._modal_renderer is not None:
            self._modal_renderer.dispose()
            self._modal_renderer = None
            if dpg.does_item_exist("chart.preview.modal"):
                dpg.delete_item("chart.preview.modal")

    def preview_task(self) -> Callable[[], ChartSpec] | None:
        return None

    def _show_preview(self) -> None:
        task = self.preview_task()
        if task is None:
            return
        try:
            spec = task()
        except ValueError as error:
            self.log(_("ERROR: {error}").format(error=error))
            return
        self.show_chart_preview(spec)

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

    def add_info_checkbox(self, parent: str | int) -> None:
        tag = self._workflow().export.replace(".export", ".info")
        dpg.add_checkbox(
            label=_("Include info sheet"),
            tag=tag,
            default_value=self.settings.get("main/include_info_sheet", False),
            callback=lambda sender, enabled: self.settings.set("main/include_info_sheet", enabled),
            parent=parent,
        )
        with dpg.tooltip(tag):
            dpg.add_text(
                _("Add an 'info' worksheet with source file hashes, "
                  "settings, and processing steps"),
            )

    def submit_load(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        *,
        loading_text: str,
        failure_text: str,
    ) -> None:
        controls = self._workflow()
        self._input_loading = True
        self._input_error = None
        self.request_preview()
        busy_controls = [controls.upload, controls.export, *controls.load_extras]
        if controls.preview is not None:
            busy_controls.append(controls.preview)
        for tag in busy_controls:
            dpg.configure_item(tag, enabled=False)
        dpg.set_value(controls.status, loading_text)

        def loaded(value: Any) -> None:
            on_success(value)
            self._input_loading = False
            self._input_error = None
            self.request_preview()
            dpg.configure_item(controls.upload, enabled=True)
            dpg.configure_item(controls.export, enabled=True)
            if controls.preview is not None:
                dpg.configure_item(controls.preview, enabled=True)

        def failed(error: Exception) -> None:
            self._input_loading = False
            self._input_error = _("Unable to preview chart: input loading failed.")
            self.request_preview()
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
                {_("Excel file"): ["*.xlsx"]},
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

        def replace() -> None:
            dpg.delete_item(tag)
            callback(path)

        with dialog_window(
            label=_("Replace existing file?"),
            tag=tag,
            width=px(430),
            height=px(145),
            scale=self.display_scale,
            actions=(
                DialogAction(_("Replace"), replace, 100),
                DialogAction(_("Cancel"), lambda: dpg.delete_item(tag), 100),
            ),
        ):
            dpg.add_text(
                _("{name} already exists. Replace it?").format(name=path.name),
                wrap=px(390),
            )

    def show_chart_preview(self, spec: ChartSpec) -> None:
        px = self.display_scale.pixels
        tag = "chart.preview.modal"
        self.close_chart_preview()
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        width, height = px(760), px(600)
        with dialog_window(
            label=_("Chart preview"),
            tag=tag,
            width=width,
            height=height,
            scale=self.display_scale,
            actions=(DialogAction(_("Close"), self.close_chart_preview),),
        ):
            self._modal_renderer = ChartRenderer(f"{tag}.body")
            self._modal_renderer.render(spec)
