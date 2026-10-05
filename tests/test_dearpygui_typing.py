"""Check local stub contracts against real widgets, without a render loop."""

from contextlib import AbstractContextManager

import dearpygui.dearpygui as dpg


def test_context_manager_and_child_slot_types_match_runtime():
    dpg.create_context()
    try:
        # These assignments also serve as static regression checks in Pyright.
        window_context: AbstractContextManager[int | str] = dpg.window(tag="typing.window")
        with window_context as window:
            group_context: AbstractContextManager[int | str] = dpg.group()
            with group_context as group:
                text = dpg.add_text("typing contract")
        slots: dict[int, list[int]] = dpg.get_item_children(window)
        children: list[int] = dpg.get_item_children(group, 1)
        assert children == [text]
        assert slots[1] == [group]
        assert dpg.get_item_parent(window) is None
        assert dpg.get_item_callback(text) is None
        dpg.set_item_pos(group, (10, 20))
        dpg.set_item_width(group, 120)
        assert dpg.get_item_width(group) == 120
        dpg.hide_item(group)
        assert not dpg.is_item_shown(group)
        dpg.show_item(group)
        header_context: AbstractContextManager[int | str] = dpg.collapsing_header(parent=window)
        with header_context as header:
            assert dpg.is_item_container(header)
    finally:
        dpg.destroy_context()
