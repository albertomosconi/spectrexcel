from contextlib import contextmanager
from dataclasses import dataclass, field
from collections.abc import Callable, Generator

import dearpygui.dearpygui as dpg

from spectrexcel.dpi import DisplayScale


@dataclass(frozen=True)
class DialogAction:
    label: str
    callback: Callable[[], None]
    width: int = 90
    tag: str | int = 0


@dataclass(frozen=True)
class DialogLayout:
    width: int
    height: int
    scale: DisplayScale
    actions: tuple[DialogAction, ...]
    wrap_widths: dict[int, int] = field(default_factory=dict)


def _geometry(layout: DialogLayout) -> dict:
    viewport_width = max(1, dpg.get_viewport_client_width())
    viewport_height = max(1, dpg.get_viewport_client_height())
    margin = layout.scale.pixels(10)
    width = min(layout.width, max(1, viewport_width - 2 * margin))
    height = min(layout.height, max(1, viewport_height - 2 * margin))
    return {
        "width": width,
        "height": height,
        "pos": ((viewport_width - width) // 2, (viewport_height - height) // 2),
    }


def _fit_content(tag: str | int, layout: DialogLayout, width: int) -> None:
    px = layout.scale.pixels
    # Leave room for window padding and the body's vertical scrollbar.
    wrap = max(1, width - px(56))

    def fit_text(parent: str | int, available: int) -> None:
        horizontal = dpg.get_item_configuration(parent).get("horizontal", False)
        offset = 0
        for child in dpg.get_item_children(parent, 1) or ():
            config = dpg.get_item_configuration(child)
            child_width = max(1, available - offset)
            if dpg.get_item_info(child)["type"] == "mvAppItemType::mvChildWindow":
                # Bordered children add their own padding and scrollbar.
                inset = px(56) if config["border"] else px(20)
                child_width = max(1, child_width - inset)
            if "wrap" in config and config["wrap"] > 0:
                preferred = layout.wrap_widths.setdefault(child, config["wrap"])
                dpg.configure_item(child, wrap=min(preferred, child_width))
            fit_text(child, child_width)
            if horizontal:
                offset += max(0, config["width"]) + px(8)

    fit_text(f"{tag}.body", wrap)
    buttons = dpg.get_item_children(f"{tag}.actions", 1)
    available = max(1, width - px(36) - px(8) * (len(buttons) - 1))
    total = sum(px(action.width) for action in layout.actions)
    ratio = min(1, available / total) if total else 1
    for button, action in zip(buttons, layout.actions):
        dpg.configure_item(button, width=max(1, int(px(action.width) * ratio)))


@contextmanager
def dialog_window(
    *,
    label: str,
    tag: str,
    width: int,
    height: int,
    scale: DisplayScale,
    actions: tuple[DialogAction, ...],
) -> Generator[None, None, None]:
    """Keep scrollable dialog content separate from always-visible actions."""
    layout = DialogLayout(width, height, scale, actions)
    with dpg.window(
        label=label,
        tag=tag,
        modal=True,
        no_move=True,
        no_resize=True,
        no_collapse=True,
        no_close=True,
        no_scrollbar=True,
        no_scroll_with_mouse=True,
        min_size=(1, 1),
        user_data=layout,
        **_geometry(layout),
    ):
        with dpg.child_window(
            tag=f"{tag}.body", width=-1, height=-scale.pixels(45),
            border=False, horizontal_scrollbar=True,
        ):
            yield
        with dpg.group(tag=f"{tag}.actions", horizontal=True):
            for action in actions:
                dpg.add_button(
                    label=action.label, callback=action.callback,
                    width=scale.pixels(action.width), tag=action.tag,
                )
    _fit_content(tag, layout, _geometry(layout)["width"])


def maintain_dialogs() -> None:
    """Re-fit open dialogs before rendering, including after viewport resize."""
    for window in dpg.get_windows():
        layout = dpg.get_item_user_data(window)
        if not isinstance(layout, DialogLayout):
            continue
        geometry = _geometry(layout)
        config = dpg.get_item_configuration(window)
        if (
            config["width"] != geometry["width"]
            or config["height"] != geometry["height"]
            or tuple(dpg.get_item_pos(window)) != geometry["pos"]
        ):
            dpg.configure_item(window, **geometry)
            _fit_content(dpg.get_item_alias(window), layout, geometry["width"])
