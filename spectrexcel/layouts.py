"""Layout preferences and persistent, resizable assay containers."""

import dearpygui.dearpygui as dpg

from spectrexcel.dpi import DisplayScale

PARAMETERS_ONLY = "parameters_only"
PARAMETERS_PREVIEW = "parameters_preview"
LAYOUT_LABELS = {
    PARAMETERS_ONLY: "parameters only",
    PARAMETERS_PREVIEW: "parameters + preview",
}


def resolve_layout(value: object) -> str:
    return value if isinstance(value, str) and value in LAYOUT_LABELS else PARAMETERS_ONLY


class AssayLayout:
    """Resize existing panes, never rebuild their children."""

    def __init__(self, parent: str | int, display_scale: DisplayScale) -> None:
        self.parent = parent
        self.scale = display_scale
        self.layout = PARAMETERS_ONLY
        self._geometry: tuple[int, int, str] | None = None
        px = self.scale.pixels
        self._themes: list[int] = []
        for padding in (0, 10):
            with dpg.theme() as theme:
                with dpg.theme_component(dpg.mvChildWindow):
                    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(padding), px(padding))
                    # Hide outlines without changing child padding or scroll geometry.
                    dpg.add_theme_color(dpg.mvThemeCol_Border, (0, 0, 0, 0))
            self._themes.append(theme)
        with dpg.group(parent=parent, horizontal=True, horizontal_spacing=px(8)) as group:
            self.group = group
            self.parameters = dpg.add_child_window(width=-1, height=-1, border=False)
            self.preview = dpg.add_child_window(width=px(300), height=-1, show=False)
        dpg.configure_item(parent, no_scrollbar=True, no_scroll_with_mouse=True)
        self.apply(PARAMETERS_ONLY)

    @property
    def content_width(self) -> int:
        width = dpg.get_item_configuration(self.parameters)["width"]
        padding = self.scale.pixels(20) if self.layout == PARAMETERS_PREVIEW else 0
        # Reserve space for the parameter pane's vertical scrollbar.
        return max(self.scale.pixels(48), width - padding - self.scale.pixels(16))

    def apply(self, layout: str) -> None:
        self.layout = resolve_layout(layout)
        embedded = self.layout == PARAMETERS_PREVIEW
        dpg.configure_item(self.preview, show=embedded)
        dpg.configure_item(self.parameters, border=embedded)
        dpg.bind_item_theme(self.parameters, self._themes[1 if embedded else 0])
        dpg.bind_item_theme(self.preview, self._themes[1])
        self._geometry = None
        self.maintain()

    def maintain(self) -> None:
        available = dpg.get_item_state(self.parent).get("content_region_avail")
        width, height = available if available is not None else dpg.get_item_rect_size(self.parent)
        if width <= 0 or height <= 0:
            return
        width, height = max(1, int(width)), max(1, int(height))
        geometry = (width, height, self.layout)
        if geometry == self._geometry:
            return
        self._geometry = geometry
        if self.layout == PARAMETERS_PREVIEW:
            pane_width = max(1, (width - self.scale.pixels(8)) // 2)
            dpg.configure_item(self.parameters, width=pane_width, height=height)
            dpg.configure_item(self.preview, width=pane_width, height=height)
        else:
            dpg.configure_item(self.parameters, width=width, height=height)

    def dispose(self) -> None:
        for theme in self._themes:
            if dpg.does_item_exist(theme):
                dpg.delete_item(theme)
        self._themes.clear()
