from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any

import dearpygui.dearpygui as dpg

from spectrexcel.dpi import DisplayScale
from spectrexcel.dialogs import DialogAction, dialog_window
from spectrexcel import native_dialogs
from spectrexcel.appearance import SEMANTIC_TEXT_COLORS
from spectrexcel.i18n import _
from spectrexcel.settings import Settings
from spectrexcel.charts import ChartRenderer, ChartSeries, ChartSpec, green_shades
from spectrexcel.layouts import AssayLayout, PARAMETERS_ONLY, PARAMETERS_PREVIEW, resolve_layout

# The tab-bar chrome themes are created once per DPG context and shared by all
# assay views: their styles use fixed tags, and a view must never delete them
# while another view is still alive.
CHROME_HEADER_THEME = "chrome.tabs.header_theme"
CHROME_TAB_THEME = "chrome.tabs.tab_theme"


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
        self._layout_fields: list[tuple[str | int, int, str, str | int | None, str | None]] = []
        self._preview_message: str | int | None = None
        self._preview_generation = 0
        self._preview_dirty = False
        self._preview_running = False
        self._input_loading = False
        self._input_error: str | None = None
        self._preview_tab = 0
        self._preview_title: str | int | None = None
        self._preview_tab_bar: list[str | int] = []
        self._modal_tab_bar: list[str | int] = []
        self._chrome_themes: list[str | int] = []

    def build(self, parent: str | int) -> None:
        raise NotImplementedError

    def preview_tab_labels(self) -> list[str]:
        """Tabs of the shared tab bar; each will show its own chart later."""
        return []

    def _ensure_chrome_themes(self) -> None:
        if dpg.does_item_exist(CHROME_TAB_THEME):
            self._chrome_themes = [CHROME_HEADER_THEME, CHROME_TAB_THEME]
            return
        px = self.display_scale.pixels
        accent = SEMANTIC_TEXT_COLORS["Dark"]["accent"]
        if dpg.does_item_exist("theme.accent.color"):
            accent = tuple(dpg.get_value("theme.accent.color"))
        with dpg.theme(tag=CHROME_HEADER_THEME):
            with dpg.theme_component(dpg.mvTable):
                dpg.add_theme_style(dpg.mvStyleVar_CellPadding, 0, 0)
        with dpg.theme(tag=CHROME_TAB_THEME):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_style(
                    dpg.mvStyleVar_FramePadding, px(10), px(3),
                    tag="chrome.tabs.frame.padding",
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_Text, accent, tag="chrome.tabs.accent.color"
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_Button, (0, 0, 0, 0), tag="chrome.tabs.background"
                )
                for color in (
                    dpg.mvThemeCol_ButtonHovered,
                    dpg.mvThemeCol_ButtonActive,
                ):
                    dpg.add_theme_color(color, (0, 0, 0, 0))
        self._chrome_themes = [CHROME_HEADER_THEME, CHROME_TAB_THEME]

    def mount(self, parent: str | int, layout: str) -> None:
        self._assay_layout = AssayLayout(parent, self.display_scale)
        self.build(self._assay_layout.parameters)
        labels = self.preview_tab_labels()
        preview = self._assay_layout.preview
        if labels:
            self._ensure_chrome_themes()
            with dpg.table(
                header_row=False,
                no_pad_outerX=True,
                policy=dpg.mvTable_SizingStretchProp,
                parent=preview,
            ) as header:
                dpg.bind_item_theme(header, self._chrome_themes[0])
                dpg.add_table_column(width_stretch=True, init_width_or_weight=1)
                dpg.add_table_column(width_fixed=True)
                with dpg.table_row():
                    self._preview_title = dpg.add_text(_("PREVIEW"))
                    dpg.bind_item_theme(self._preview_title, "theme.accent")
                    self._preview_tab_bar = self._build_tab_bar(labels, self._select_tab)
        self._preview_message = dpg.add_text("", parent=preview)
        self._embedded_renderer = ChartRenderer(preview, self.display_scale)
        self.apply_layout(layout)

    def _select_tab(self, index: int) -> None:
        if index != self._preview_tab:
            self._preview_tab = index
            self.request_preview()

    def _dialog_tab_selected(self, index: int) -> None:
        if index == self._preview_tab:
            return
        self._preview_tab = index
        task = self.preview_task(index)
        if task is None or self._modal_renderer is None:
            return
        try:
            spec = task()
        except ValueError as error:
            self.log(_("ERROR: {error}").format(error=error))
            return
        self._modal_renderer.render(spec)

    def _build_tab_bar(self, labels: list[str], on_select: Callable[[int], None]) -> list[str | int]:
        """Text-like buttons styled as tabs, placed in the current container."""
        px = self.display_scale.pixels
        buttons: list[str | int] = []
        with dpg.group(horizontal=True, horizontal_spacing=px(14)):
            for index, label in enumerate(labels):
                button = dpg.add_button(
                    label=label,
                    callback=lambda *_args, tab=index: on_select(tab),
                    user_data=index,
                )
                dpg.bind_item_theme(button, self._chrome_themes[1])
                buttons.append(button)
        return buttons

    def register_layout_row(self, tag: str | int) -> None:
        self._layout_rows.append(tag)

    def register_layout_field(
        self, tag: str | int, width: int, label: str = "", group: str | None = None
    ) -> None:
        heading = None
        if label:
            heading = dpg.add_text(
                label, parent=dpg.get_item_parent(tag) or 0, before=tag, show=False,
            )
        # Fields sharing ``group`` keep a side-by-side layout: fit_embedded_fields
        # scales the pair (or row) down to the pane's content width.
        self._layout_fields.append((tag, width, label, heading, group))

    def apply_layout(self, layout: str) -> None:
        self.close_chart_preview()
        self.layout = resolve_layout(layout)
        if self._assay_layout is None:
            return
        embedded = self.layout == PARAMETERS_PREVIEW
        self._assay_layout.apply(self.layout)
        for row in self._layout_rows:
            dpg.configure_item(row, horizontal=not embedded)
        for tag, width, label, heading, _group in self._layout_fields:
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
        task = self.preview_task(self._preview_tab)
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

    def maintain_charts(self) -> None:
        if self._embedded_renderer is not None:
            self._embedded_renderer.maintain()
        if self._modal_renderer is not None:
            self._modal_renderer.maintain()

    def maintain_layout(self) -> None:
        if self._assay_layout is None:
            return
        self._assay_layout.maintain()
        embedded = self.layout == PARAMETERS_PREVIEW
        width = self._assay_layout.content_width
        spacing = self.display_scale.pixels(8)
        pending: list[tuple[str | int, int]] = []
        pending_group: str | None = None
        for tag, logical_width, _label, _heading, group in self._layout_fields:
            if embedded and group is not None and group == pending_group:
                pending.append((tag, logical_width))
            else:
                self._fit_embedded_fields(pending, spacing, width)
                pending = [(tag, logical_width)] if embedded and group is not None else []
                pending_group = group
                field_width = self.display_scale.pixels(logical_width)
                dpg.configure_item(
                    tag, width=min(field_width, width) if embedded else field_width
                )
        self._fit_embedded_fields(pending, spacing, width)
        dpg.configure_item(self._workflow().status, wrap=width if embedded else -1)
        if self._preview_message is not None:
            dpg.configure_item(self._preview_message, wrap=width)

    def _fit_embedded_fields(
        self, pending: list[tuple[str | int, int]], spacing: int, available: int
    ) -> None:
        """Shrink a group of side-by-side fields proportionally to fit ``available``."""
        if len(pending) <= 1:
            return
        px = self.display_scale.pixels
        total = sum(px(logical_width) for _tag, logical_width in pending)
        if total <= 0:
            return
        room = max(0, available - spacing * len(pending))
        factor = 1.0 if total <= room else room / total
        for tag, logical_width in pending:
            dpg.configure_item(tag, width=int(px(logical_width) * factor))

    def dispose(self) -> None:
        self.active = False
        self._preview_generation += 1
        self.close_chart_preview()
        if self._embedded_renderer is not None:
            self._embedded_renderer.dispose()
        if self._assay_layout is not None:
            self._assay_layout.dispose()
        self._chrome_themes = []
        self._preview_title = None
        self._preview_tab_bar = []
        self._modal_tab_bar = []

    def close_chart_preview(self) -> None:
        self._modal_tab_bar = []
        if self._modal_renderer is not None:
            self._modal_renderer.dispose()
            self._modal_renderer = None
            if dpg.does_item_exist("chart.preview.modal"):
                dpg.delete_item("chart.preview.modal")

    def preview_task(self, tab: int = 0) -> Callable[[], ChartSpec] | None:
        return None

    def _show_preview(self) -> None:
        task = self.preview_task(self._preview_tab)
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
        labels = self.preview_tab_labels()
        self._ensure_chrome_themes()
        with dialog_window(
            label=_("Chart preview"),
            tag=tag,
            width=width,
            height=height,
            scale=self.display_scale,
            actions=(DialogAction(_("Close"), self.close_chart_preview),),
        ):
            if labels:
                self._modal_tab_bar = self._build_tab_bar(
                    labels, self._dialog_tab_selected
                )
            self._modal_renderer = ChartRenderer(f"{tag}.body", self.display_scale)
            self._modal_renderer.render(spec)
