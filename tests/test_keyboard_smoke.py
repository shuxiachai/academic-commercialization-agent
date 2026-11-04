"""e2e/keyboard_smoke.py drives the page with the keyboard and nothing else (#237).

The smoke only means "a keyboard-only user can do this" while every move and
every activation in it is a key press from its KEYS set. One element.click(),
fill(), select_option() or programmatic focus() would let a journey pass that
no keyboard user could repeat, and the smoke would still print "passed". This
reads the smoke's source, so it runs in every pytest cell rather than only in
the browser job.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SMOKE = Path(__file__).resolve().parents[1] / "e2e" / "keyboard_smoke.py"
KEYS = {"Tab", "Shift+Tab", "Enter", "Space", "Escape"}
# Playwright calls that operate a page some other way than a key press.
DRIVERS = {"click", "dblclick", "tap", "fill", "clear", "check", "uncheck", "set_checked", "select_option",
           "set_input_files", "focus", "blur", "hover", "drag_to", "dispatch_event", "insert_text", "down", "up"}
# The same, from inside the JavaScript the smoke evaluates.
SCRIPT_DRIVERS = (".click(", ".focus(", ".blur(", "dispatchEvent(", "requestSubmit(", ".submit(", ".value =")


def _violations(source: str) -> list[str]:
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"mouse", "touchscreen"}:
            found.append(f"line {node.lineno}: page.{node.attr}")
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        name, owner = node.func.attr, ast.unparse(node.func.value)
        if name in DRIVERS:
            found.append(f"line {node.lineno}: {owner}.{name}()")
        elif name == "press":
            # keyboard.press only inside Keyboard.press, which checks KEYS itself.
            if owner == "self.page.keyboard":
                continue
            if owner not in {"keys", "self.keys"}:
                found.append(f"line {node.lineno}: {owner}.press()")
            elif not (node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in KEYS):
                found.append(f"line {node.lineno}: {owner}.press({ast.unparse(node.args[0]) if node.args else ''})")
        elif name == "type" and owner not in {"keys", "self.page.keyboard"}:
            found.append(f"line {node.lineno}: {owner}.type()")
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and ast.get_docstring(node)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found += [f"line {node.lineno}: script calls {call}" for call in SCRIPT_DRIVERS if call in node.value]
    return found


def test_the_keyboard_smoke_presses_only_its_keys():
    source = SMOKE.read_text(encoding="utf-8")
    assert 'KEYS = frozenset({"Tab", "Shift+Tab", "Enter", "Space", "Escape"})' in source
    assert _violations(source) == []


@pytest.mark.parametrize("line", [
    'page.locator("#run-btn").click()',
    'page.locator("#topic").fill("topic")',
    'page.locator("#byok-provider").select_option("qwen")',
    'page.locator("#mobile-menu").focus()',
    'page.mouse.click(10, 10)',
    'page.keyboard.press("ArrowDown")',
    'keys.press("ArrowDown")',
    'keys.press(key)',
    'page.locator("#topic").press("Enter")',
    'page.evaluate("() => document.querySelector(\'#run-btn\').click()")',
    'page.evaluate("() => document.activeElement.form.requestSubmit()")',
])
def test_a_mouse_or_scripted_step_is_reported(line):
    """Negative controls: each of these would make a journey pass without a keyboard user."""
    source = SMOKE.read_text(encoding="utf-8").replace(
        "    keys = Keyboard(page)\n", f"    keys = Keyboard(page)\n    {line}\n", 1)
    assert line in source
    assert _violations(source)
