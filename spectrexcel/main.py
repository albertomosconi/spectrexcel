import importlib.metadata
import queue
import sys
import webbrowser
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Callable

import dearpygui.dearpygui as dpg

from spectrexcel.assays import BindingTitolazione, Cinetiche, FamigliaDiSpettri
from spectrexcel.assays.shared import AssayView
from spectrexcel.appearance import THEME_OPTIONS, resolve_theme
from spectrexcel.dpi import DisplayScale, configure_display_scale
from spectrexcel.settings import Settings
from spectrexcel.updater import (
    REPOSITORY_URL,
    PreparedUpdate,
    UpdateRelease,
    confirm_update_startup,
    find_update,
    launch_replacement,
    prepare_update,
)


@dataclass(frozen=True)
class Assay:
    name: str
    view: type[AssayView]


ASSAYS = (
    Assay("binding / titolazione", BindingTitolazione),
    Assay("cinetiche", Cinetiche),
    Assay("famiglia di spettri", FamigliaDiSpettri),
)

GEAR_ICON = (
    "    #####    ",
    " ##  ###  ## ",
    " ### ### ### ",
    "  #########  ",
    "  ###   ###  ",
    "####     ####",
    "####     ####",
    "####     ####",
    "  ###   ###  ",
    "  #########  ",
    " ### ### ### ",
    " ##  ###  ## ",
    "    #####    ",
)

THEME_COLORS = {
    "Dark": {
        "Text": (235, 235, 235),
        "TextDisabled": (135, 135, 135),
        "WindowBg": (24, 27, 32),
        "ChildBg": (30, 34, 40),
        "PopupBg": (30, 34, 40),
        "Border": (65, 70, 78),
        "FrameBg": (42, 47, 55),
        "FrameBgHovered": (52, 59, 69),
        "FrameBgActive": (62, 70, 82),
        "Button": (36, 91, 130),
        "ButtonHovered": (46, 116, 163),
        "ButtonActive": (31, 78, 111),
        "Header": (36, 91, 130),
        "HeaderHovered": (46, 116, 163),
        "HeaderActive": (31, 78, 111),
        "CheckMark": (104, 190, 255),
        "Separator": (65, 70, 78),
        "ScrollbarBg": (24, 27, 32),
        "ScrollbarGrab": (72, 78, 88),
        "TableBorderStrong": (65, 70, 78),
        "TableBorderLight": (50, 55, 63),
    },
    "Light": {
        "Text": (255, 255, 255),
        "TextDisabled": (205, 215, 222),
        "WindowBg": (244, 246, 248),
        "ChildBg": (252, 252, 253),
        "PopupBg": (252, 252, 253),
        "Border": (180, 185, 192),
        "FrameBg": (36, 91, 130),
        "FrameBgHovered": (46, 116, 163),
        "FrameBgActive": (31, 78, 111),
        "Button": (36, 91, 130),
        "ButtonHovered": (46, 116, 163),
        "ButtonActive": (31, 78, 111),
        "Header": (36, 91, 130),
        "HeaderHovered": (46, 116, 163),
        "HeaderActive": (31, 78, 111),
        "CheckMark": (255, 255, 255),
        "Separator": (180, 185, 192),
        "ScrollbarBg": (235, 238, 241),
        "ScrollbarGrab": (170, 176, 184),
        "TableBorderStrong": (180, 185, 192),
        "TableBorderLight": (210, 214, 220),
    },
}

SEMANTIC_TEXT_COLORS = {
    "Dark": {"accent": (104, 190, 255), "muted": (150, 150, 150)},
    "Light": {"accent": (24, 91, 138), "muted": (95, 100, 108)},
}


class SpectrExcelApp:
    def __init__(self, version: str, display_scale: DisplayScale) -> None:
        self.version = version
        self.display_scale = display_scale
        self.settings = Settings()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="spectrexcel")
        self.results: queue.SimpleQueue[
            tuple[Callable[[Any], None], Any, Exception | None]
        ] = queue.SimpleQueue()
        self.futures: set[Future[Any]] = set()
        self.futures_lock = Lock()
        self.latest_release: UpdateRelease | None = None
        self.assay_view: AssayView | None = None
        self.log_scroll_pending = 0
        self.theme_preference = self.settings.get("main/theme", "System")
        if self.theme_preference not in THEME_OPTIONS:
            self.theme_preference = "System"
        self.active_theme = "Dark"

    def build(self) -> None:
        px = self.display_scale.pixels
        font_path = Path(__file__).parent / "fonts" / "InterVariable.ttf"
        log_font_path = Path(__file__).parent / "fonts" / "JetBrainsMono-Regular.ttf"
        with dpg.font_registry():
            default_font = dpg.add_font(str(font_path), px(16), tag="main.font")
            dpg.add_font(str(log_font_path), px(16), tag="main.log_font")
        dpg.bind_font(default_font)

        for name, colors in THEME_COLORS.items():
            with dpg.theme(tag=f"theme.{name.lower()}"):
                with dpg.theme_component(dpg.mvAll):
                    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(18), px(16))
                    dpg.add_theme_style(dpg.mvStyleVar_FramePadding, px(10), px(6))
                    dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, px(8), px(7))
                    dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, px(4))
                    for color, value in colors.items():
                        dpg.add_theme_color(getattr(dpg, f"mvThemeCol_{color}"), value)
                with dpg.theme_component(dpg.mvButton):
                    dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255))
                    dpg.add_theme_color(
                        dpg.mvThemeCol_TextDisabled,
                        (205, 215, 222) if name == "Light" else (135, 135, 135),
                    )
                for control in (
                    dpg.mvCombo,
                    dpg.mvInputText,
                    dpg.mvInputInt,
                    dpg.mvInputFloat,
                    dpg.mvInputDouble,
                ):
                    with dpg.theme_component(control):
                        dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255))
                        dpg.add_theme_color(
                            dpg.mvThemeCol_TextDisabled,
                            (205, 215, 222) if name == "Light" else (135, 135, 135),
                        )
                        if control == dpg.mvCombo:
                            dpg.add_theme_color(
                                dpg.mvThemeCol_PopupBg, (36, 91, 130)
                            )
                with dpg.theme_component(dpg.mvText):
                    dpg.add_theme_color(
                        dpg.mvThemeCol_Text,
                        (30, 34, 40) if name == "Light" else (235, 235, 235),
                    )

        with dpg.theme(tag="theme.accent"):
            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_color(
                    dpg.mvThemeCol_Text,
                    SEMANTIC_TEXT_COLORS["Dark"]["accent"],
                    tag="theme.accent.color",
                )
        with dpg.theme(tag="theme.muted"):
            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_color(
                    dpg.mvThemeCol_Text,
                    SEMANTIC_TEXT_COLORS["Dark"]["muted"],
                    tag="theme.muted.color",
                )
        self._apply_theme()

        gear_pixels = [
            channel
            for row in GEAR_ICON
            for pixel in row
            for channel in ((1.0, 1.0, 1.0, 1.0) if pixel == "#" else (0.0,) * 4)
        ]
        with dpg.texture_registry():
            dpg.add_static_texture(13, 13, gear_pixels, tag="main.gear.texture")

        with dpg.theme() as header_theme:
            with dpg.theme_component(dpg.mvTable):
                dpg.add_theme_style(dpg.mvStyleVar_CellPadding, 0, px(4))

        with dpg.theme() as log_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, px(8), 0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(8), px(4))

        with dpg.window(
            tag="main.window",
            no_title_bar=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
        ):
            with dpg.table(
                tag="main.header",
                header_row=False,
                policy=dpg.mvTable_SizingStretchProp,
                no_pad_outerX=True,
            ):
                dpg.add_table_column(width_stretch=True, init_width_or_weight=1)
                dpg.add_table_column(width_fixed=True)
                dpg.add_table_column(width_fixed=True)
                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("ASSAY")
                        selected_index = self.settings.get("main/selected_assay", 0)
                        if not 0 <= selected_index < len(ASSAYS):
                            selected_index = 0
                        dpg.add_combo(
                            items=[assay.name for assay in ASSAYS],
                            default_value=ASSAYS[selected_index].name,
                            tag="main.assay",
                            callback=self._assay_changed,
                            width=px(250),
                        )
                    version_text = dpg.add_text(f"v{self.version}")
                    dpg.bind_item_theme(version_text, "theme.muted")
                    with dpg.group(horizontal=True, horizontal_spacing=0):
                        dpg.add_spacer(width=px(4))
                        dpg.add_button(
                            label="Check updates",
                            tag="main.update",
                            callback=self._check_and_download_update,
                        )
                        dpg.add_spacer(width=px(4))
                        dpg.add_image_button(
                            "main.gear.texture",
                            tag="main.settings",
                            callback=self._show_settings,
                            width=px(16),
                            height=px(16),
                            tint_color=(235, 235, 235),
                        )
                        with dpg.tooltip("main.settings"):
                            dpg.add_text("App settings")
            dpg.bind_item_theme("main.header", header_theme)

            dpg.add_separator()
            with dpg.child_window(tag="assay.content", height=px(-174), border=False):
                pass

            activity_title = dpg.add_text("ACTIVITY")
            dpg.bind_item_theme(activity_title, "theme.accent")
            dpg.add_child_window(
                tag="main.log",
                height=px(105),
                width=-1,
                horizontal_scrollbar=True,
            )
            dpg.bind_item_theme("main.log", log_theme)
            dpg.add_text("", tag="main.log.text", parent="main.log")
            dpg.bind_item_font("main.log.text", "main.log_font")
            with dpg.group(horizontal=True):
                developer_text = dpg.add_text("Developed by Alberto Mosconi")
                dpg.bind_item_theme(developer_text, "theme.muted")
                dpg.add_button(label="Source code", small=True, callback=self._open_source)
                license_text = dpg.add_text("GPLv3 or later")
                dpg.bind_item_theme(license_text, "theme.muted")

        dpg.set_primary_window("main.window", True)
        dpg.configure_item(
            "main.window", no_scrollbar=True, no_scroll_with_mouse=True
        )
        self._load_assay(selected_index)
        self.submit(self._find_update, self._update_check_finished, self._update_check_failed)

    def _apply_theme(self) -> None:
        self.active_theme = resolve_theme(self.theme_preference)
        dpg.bind_theme(f"theme.{self.active_theme.lower()}")
        semantic_colors = SEMANTIC_TEXT_COLORS[self.active_theme]
        dpg.set_value("theme.accent.color", semantic_colors["accent"])
        dpg.set_value("theme.muted.color", semantic_colors["muted"])

    def _show_settings(self) -> None:
        px = self.display_scale.pixels
        width, height = px(430), px(190)
        if dpg.does_item_exist("settings.modal"):
            dpg.delete_item("settings.modal")
        position = (
            max(0, (dpg.get_viewport_client_width() - width) // 2),
            max(0, (dpg.get_viewport_client_height() - height) // 2),
        )
        with dpg.window(
            label="App settings",
            tag="settings.modal",
            modal=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
            no_close=True,
            width=width,
            height=height,
            pos=position,
        ):
            dpg.add_combo(
                label="Theme",
                items=list(THEME_OPTIONS),
                default_value=self.theme_preference,
                callback=self._theme_changed,
                width=px(180),
            )
            dpg.add_text(
                "System is detected now. Restart or reselect System after changing your OS theme.",
                tag="settings.system_note",
                show=self.theme_preference == "System",
                wrap=px(390),
            )
            dpg.add_spacer(height=px(10))
            dpg.add_button(
                label="Close",
                callback=lambda: dpg.delete_item("settings.modal"),
                width=px(90),
            )

    def _theme_changed(self, _sender: Any, preference: str) -> None:
        if preference not in THEME_OPTIONS:
            return
        self.theme_preference = preference
        if not self.settings.set("main/theme", preference):
            self.log("ERROR: unable to save the theme preference")
        self._apply_theme()
        dpg.configure_item("settings.system_note", show=preference == "System")

    def submit(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        future = self.executor.submit(task)
        with self.futures_lock:
            self.futures.add(future)

        def completed(done: Future[Any]) -> None:
            with self.futures_lock:
                self.futures.discard(done)
            try:
                self.results.put((on_success, done.result(), None))
            except Exception as error:
                self.results.put((on_error, None, error))

        future.add_done_callback(completed)

    def has_running_tasks(self) -> bool:
        with self.futures_lock:
            return any(not future.done() for future in self.futures)

    def process_results(self) -> None:
        while True:
            try:
                callback, value, error = self.results.get_nowait()
            except queue.Empty:
                return
            if error is None:
                try:
                    callback(value)
                except Exception as callback_error:
                    self.log(f"ERROR: {callback_error}")
            else:
                try:
                    callback(error)
                except Exception as callback_error:
                    self.log(f"ERROR: {callback_error}")

    def log(self, text: str | list[str]) -> None:
        messages = [text] if isinstance(text, str) else text
        at_bottom = (
            dpg.get_y_scroll_max("main.log") - dpg.get_y_scroll("main.log") <= 2
            or self.log_scroll_pending > 0
        )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_lines = "\n".join(f"[ {timestamp} ] {message}" for message in messages)
        current = dpg.get_value("main.log.text")
        dpg.set_value("main.log.text", f"{current}\n{new_lines}" if current else new_lines)
        if at_bottom:
            # The new scroll maximum is available after the next rendered frame.
            self.log_scroll_pending = 2

    def maintain_log_scroll(self) -> None:
        if self.log_scroll_pending == 0:
            return
        dpg.set_y_scroll("main.log", dpg.get_y_scroll_max("main.log"))
        self.log_scroll_pending -= 1

    def _assay_changed(self, _sender: Any, assay_name: str) -> None:
        index = next(
            index for index, assay in enumerate(ASSAYS) if assay.name == assay_name
        )
        self._load_assay(index)

    def _load_assay(self, index: int) -> None:
        if self.assay_view is not None:
            self.assay_view.dispose()
        dpg.delete_item("assay.content", children_only=True)
        assay = ASSAYS[index]
        self.assay_view = assay.view(
            self.log, self.submit, self.settings, self.display_scale
        )
        self.assay_view.build("assay.content")
        self.settings.set("main/selected_assay", index)
        self.log(f"LOADED ASSAY: {assay.name}")

    def _find_update(self) -> UpdateRelease | None:
        return find_update(self.version)

    def _update_check_finished(self, release: UpdateRelease | None) -> None:
        self.latest_release = release
        if release is not None:
            dpg.configure_item("main.update", label=f"Update {release.tag}")

    def _update_check_failed(self, _error: Exception) -> None:
        # Startup update checks are intentionally silent.
        pass

    def _check_and_download_update(self) -> None:
        dpg.configure_item("main.update", enabled=False, label="Checking...")
        self.log("checking for updates...")
        self.submit(self._find_update, self._manual_update_finished, self._manual_update_failed)

    def _manual_update_finished(self, release: UpdateRelease | None) -> None:
        dpg.configure_item("main.update", enabled=True)
        self.latest_release = release
        if release is None:
            dpg.configure_item("main.update", label="Check updates")
            self.log("no updates found")
            return
        dpg.configure_item("main.update", label=f"Update {release.tag}")
        self.log(f"NEW APP VERSION FOUND: {release.tag}")
        self._show_update_confirmation(release)

    def _manual_update_failed(self, error: Exception) -> None:
        dpg.configure_item("main.update", enabled=True, label="Check updates")
        self.log(f"ERROR: unable to check for updates: {error}")

    def _show_update_confirmation(self, release: UpdateRelease) -> None:
        px = self.display_scale.pixels
        if dpg.does_item_exist("settings.modal"):
            dpg.delete_item("settings.modal")
        if dpg.does_item_exist("update.modal"):
            dpg.delete_item("update.modal")
        with dpg.window(
            label="Update available",
            tag="update.modal",
            modal=True,
            no_close=True,
            width=px(470),
            height=px(180),
            pos=self.display_scale.position((165, 155)),
        ):
            dpg.add_text(
                f"Version {release.tag} is available. Install it and restart SpectrExcel?",
                wrap=px(430),
            )
            dpg.add_spacer(height=px(12))
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Install and restart",
                    callback=lambda: self._download_update(release),
                    width=px(180),
                )
                dpg.add_button(
                    label="Not now",
                    callback=lambda: dpg.delete_item("update.modal"),
                    width=px(100),
                )

    def _download_update(self, release: UpdateRelease) -> None:
        if self.has_running_tasks():
            self.log("finish the current operation before installing the update")
            return
        dpg.delete_item("update.modal")
        dpg.configure_item("main.update", enabled=False, label="Downloading...")
        self.log(f"downloading {release.asset.name}...")
        self.submit(
            lambda: prepare_update(release),
            self._update_download_finished,
            self._update_download_failed,
        )

    def _update_download_finished(self, update: PreparedUpdate) -> None:
        if self.has_running_tasks():
            update.downloaded_path.unlink(missing_ok=True)
            self._update_download_failed(
                RuntimeError("an application operation started during the download")
            )
            return
        try:
            launch_replacement(update)
        except Exception as error:
            self._update_download_failed(error)
            return
        self.log("update verified; restarting SpectrExcel...")
        dpg.stop_dearpygui()

    def _update_download_failed(self, error: Exception) -> None:
        dpg.configure_item("main.update", enabled=True, label="Check updates")
        self.log(f"ERROR: unable to install update: {error}")

    @staticmethod
    def _open_source() -> None:
        webbrowser.open(REPOSITORY_URL)

    def save_viewport(self) -> None:
        width = dpg.get_viewport_width()
        height = dpg.get_viewport_height()
        position = dpg.get_viewport_pos()
        logical = self.display_scale.logical_pixels
        self.settings.set("window/width", logical(width))
        self.settings.set("window/height", logical(height))
        self.settings.set("window/position", [logical(value) for value in position])

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)


def application_version() -> str:
    try:
        return importlib.metadata.version("spectrexcel")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def main() -> None:
    display_scale = configure_display_scale()
    dpg.create_context()
    dpg.configure_app(manual_callback_management=True)
    app = SpectrExcelApp(application_version(), display_scale)
    width = app.settings.get("window/width", 800)
    height = app.settings.get("window/height", 560)
    position = app.settings.get("window/position", [100, 100])
    if width < 1:
        width = 800
    if height < 1:
        height = 560
    if (
        len(position) != 2
        or not all(isinstance(coordinate, int) for coordinate in position)
    ):
        position = [100, 100]
    icon_path = Path(__file__).with_name("icon.ico")
    px = display_scale.pixels
    viewport_position = display_scale.position(position)

    try:
        dpg.create_viewport(
            title="SpectrExcel",
            width=px(max(width, 720)),
            height=px(max(height, 520)),
            x_pos=viewport_position[0],
            y_pos=viewport_position[1],
            min_width=px(720),
            min_height=px(520),
        )
        if icon_path.exists():
            dpg.set_viewport_large_icon(str(icon_path))
            dpg.set_viewport_small_icon(str(icon_path))
        app.build()
        dpg.setup_dearpygui()
        dpg.show_viewport()
        confirm_update_startup()
        while dpg.is_dearpygui_running():
            dpg.run_callbacks(dpg.get_callback_queue())
            app.process_results()
            dpg.render_dearpygui_frame()
            app.maintain_log_scroll()
        app.save_viewport()
    finally:
        app.shutdown()
        dpg.destroy_context()


if __name__ == "__main__":
    main()
