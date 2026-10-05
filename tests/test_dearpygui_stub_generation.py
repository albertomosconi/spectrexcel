import ast
from importlib.metadata import version
from pathlib import Path

import dearpygui.dearpygui as dpg

from scripts.generate_dearpygui_stubs import build_stub


def test_generated_stub_preserves_every_public_wrapper_and_is_current():
    assert dpg.__file__ is not None
    source_path = Path(dpg.__file__)
    source = source_path.read_text()
    native = source_path.with_name("_dearpygui.pyi").read_text()
    generated = build_stub(source, native, version("dearpygui"))
    root = Path(__file__).resolve().parents[1]
    assert (root / "typings/dearpygui/dearpygui.pyi").read_text() == generated
    native_names = {
        node.name for node in ast.parse(native).body if isinstance(node, ast.FunctionDef)
    }
    public_names = {
        node.name for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    stub_names = {
        node.name for node in ast.parse(generated).body if isinstance(node, ast.FunctionDef)
    }
    assert public_names - native_names <= stub_names


def test_generator_preserves_deprecations_and_nullable_defaults():
    source = '''
@deprecated("Use new_widget instead.")
@contextmanager
def old_widget(*, label: str = None) -> Union[int, str]:
    yield 1
'''
    generated = build_stub(source, "", "2.x")
    assert "@_deprecated('Use new_widget instead.')" in generated
    assert "label: str | None=..." in generated
    assert "AbstractContextManager[int | str]" in generated
