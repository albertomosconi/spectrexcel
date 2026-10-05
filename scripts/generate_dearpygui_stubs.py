"""Regenerate public wrapper stubs, retaining Dear PyGui's native API types.

Run with ``uv run python scripts/generate_dearpygui_stubs.py`` after upgrading
Dear PyGui. ``--check`` verifies that the checked-in stub matches installation.
Only signatures are copied; no Dear PyGui implementation is vendored.
"""

import argparse
import ast
import copy
from functools import reduce
from importlib.metadata import version
from pathlib import Path

import dearpygui.dearpygui as dpg


HEADER = '''"""Generated wrapper signatures for Dear PyGui {version}.

Regenerate: uv run python scripts/generate_dearpygui_stubs.py
Native APIs retain their bundled signatures. Wrapper context managers return
context managers, nullable defaults remain nullable, and child slots 0-3 hold
lists. Deprecated wrappers retain their upstream replacement messages.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Literal, overload
from typing_extensions import deprecated as _deprecated

from dearpygui._dearpygui import *

'''

CHILDREN = '''@overload
def get_item_children(item: int | str, slot: Literal[0, 1, 2, 3]) -> list[int]: ...
@overload
def get_item_children(item: int | str, slot: Literal[-1] = -1) -> dict[int, list[int]]: ...
@overload
def get_item_children(item: int | str, slot: int) -> dict[int, list[int]] | list[int] | None: ...
'''


class ModernAnnotations(ast.NodeTransformer):
    def visit_Subscript(self, node: ast.Subscript) -> ast.expr:
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "Union":
            members = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            return reduce(lambda left, right: ast.BinOp(left, ast.BitOr(), right), members)
        return node

    def visit_Name(self, node: ast.Name) -> ast.Name:
        replacements = {"List": "list", "Tuple": "tuple", "Dict": "dict"}
        return ast.Name(id=replacements.get(node.id, node.id), ctx=ast.Load())


def annotation(node: ast.expr | None, *, nullable: bool = False) -> ast.expr:
    result = ast.parse(ast.unparse(ModernAnnotations().visit(node)) if node else "Any", mode="eval").body
    if isinstance(result, ast.Name) and result.id == "Callable":
        result = ast.parse("Callable[..., Any]", mode="eval").body
    if nullable and ast.unparse(result) != "Any" and "None" not in ast.unparse(result):
        result = ast.BinOp(result, ast.BitOr(), ast.Constant(None))
    return result


def build_stub(public_source: str, native_source: str, installed_version: str) -> str:
    native_names = {
        node.name for node in ast.parse(native_source).body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    declarations = [HEADER.format(version=installed_version)]
    for original in ast.parse(public_source).body:
        if not isinstance(original, ast.FunctionDef):
            continue
        if original.name.startswith("_") or original.name in native_names:
            continue
        if original.name == "get_item_children":
            declarations.append(CHILDREN)
            continue
        node = copy.deepcopy(original)
        positional = node.args.posonlyargs + node.args.args
        defaults = [None] * (len(positional) - len(node.args.defaults)) + node.args.defaults
        for arg, default in zip(positional + node.args.kwonlyargs, defaults + node.args.kw_defaults):
            nullable = isinstance(default, ast.Constant) and default.value is None
            arg.annotation = annotation(arg.annotation, nullable=nullable)
        for arg in (node.args.vararg, node.args.kwarg):
            if arg is not None:
                arg.annotation = annotation(arg.annotation)
        node.args.defaults = [ast.Constant(Ellipsis) for default in node.args.defaults]
        node.args.kw_defaults = [
            ast.Constant(Ellipsis) if default is not None else None
            for default in node.args.kw_defaults
        ]
        node.returns = annotation(node.returns)
        is_context = any(isinstance(decorator, ast.Name) and decorator.id == "contextmanager"
                         for decorator in original.decorator_list)
        if is_context:
            # mutex yields lock_mutex() (None); popup may yield a string tag.
            yielded = "None" if node.name == "mutex" else "int | str"
            node.returns = ast.parse(f"AbstractContextManager[{yielded}]", mode="eval").body
        if node.name == "run_callbacks":
            node.returns = ast.Constant(None)
        if node.name == "set_item_pos":
            # configure_item accepts both list and tuple coordinates.
            node.args.args[1].annotation = ast.parse("list[float] | tuple[float, ...]", mode="eval").body
        if node.name == "plot":
            for arg in node.args.kwonlyargs:
                if arg.arg == "zoom_rate":
                    arg.annotation = ast.Name(id="float", ctx=ast.Load())
        node.decorator_list = []
        for decorator in original.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == "deprecated":
                node.decorator_list.append(ast.Call(
                    func=ast.Name(id="_deprecated", ctx=ast.Load()),
                    args=decorator.args, keywords=[],
                ))
            elif isinstance(decorator, ast.Name) and decorator.id == "deprecated":
                node.decorator_list.append(ast.Call(
                    func=ast.Name(id="_deprecated", ctx=ast.Load()),
                    args=[ast.Constant("Deprecated by Dear PyGui.")], keywords=[],
                ))
        node.body = [ast.Expr(ast.Constant(Ellipsis))]
        declaration = ast.unparse(ast.fix_missing_locations(node))
        # Each copied signature remains one line, matching the upstream generator.
        declarations.append(declaration.replace("\n    ...", " ...") + "\n")
    return "\n".join(declarations)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    assert dpg.__file__ is not None
    source = Path(dpg.__file__)
    generated = build_stub(
        source.read_text(), source.with_name("_dearpygui.pyi").read_text(), version("dearpygui"),
    )
    target = Path(__file__).resolve().parents[1] / "typings/dearpygui/dearpygui.pyi"
    if args.check:
        if target.read_text() != generated:
            parser.exit(1, "Dear PyGui stubs are stale; rerun without --check.\n")
    else:
        target.write_text(generated)


if __name__ == "__main__":
    main()
