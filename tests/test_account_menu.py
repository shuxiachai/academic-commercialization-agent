"""The account's corner of the rail, the shortcut hint, and the account panel: markup and styles.

Seen on production on 2026-11-15, signed in as an ordinary account:

- the account area was one line: "Signed in..." with the address cut off and
  three small underlined links (Account, API keys, Sign out), harder still to
  hit on a phone;
- "0/5 running" and five dots, the whole deployment's slots, were shown to
  everyone and cut off in the phone's rail;
- the "N" beside "New analysis" named a key on screens that have no keyboard;
- the account panel opened with the cursor in "Current password", and
  "Change password" was its one primary button.

The behaviour runs in tests/js/landing_contract.mjs (the account menu, the
slots line, the panel's focus). This file holds what a script cannot see in a
stand-in DOM: the roles, the sizes, the media query and the order of things.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
CSS = re.sub(r"/\*.*?\*/", "", (ROOT / "web" / "static" / "css" / "workbench.css").read_text(encoding="utf-8"), flags=re.S)
STRINGS = (ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
CJK = re.compile(r"[㐀-鿿]")


class _Tree(HTMLParser):
    """Tags in document order with their attributes and the id path above them."""

    VOID = {"input", "img", "br", "meta", "link", "path", "circle", "hr"}

    def __init__(self):
        super().__init__()
        self.stack: list[dict] = []
        self.tags: list[dict] = []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, **dict(attrs), "inside": [parent.get("id") for parent in self.stack if parent.get("id")]}
        self.tags.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for at in range(len(self.stack) - 1, -1, -1):
            if self.stack[at]["tag"] == tag:
                del self.stack[at:]
                return


TREE = _Tree()
TREE.feed(INDEX)
BY_ID = {node["id"]: node for node in TREE.tags if node.get("id")}


def rule(selector: str) -> str:
    """The declarations of the rule whose selector list is exactly `selector`."""
    found = re.search(rf"(?:^|\}})\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", CSS, re.S)
    assert found, selector
    return found[1]


def strings(key: str) -> tuple[str, str]:
    english, chinese = STRINGS.split('"Simplified Chinese": {', 1)
    pick = lambda table: re.search(rf'^\s+{key}: "((?:[^"\\]|\\.)*)"', table, re.M)[1]  # noqa: E731
    return pick(english), pick(chinese)


def test_the_account_area_is_a_button_and_a_menu():
    button, menu = BY_ID["account-menu-button"], BY_ID["account-menu"]
    assert button["tag"] == "button" and button["type"] == "button"
    assert (button["aria-haspopup"], button["aria-expanded"], button["aria-controls"]) == ("menu", "false", "account-menu")
    assert menu["role"] == "menu" and menu["aria-labelledby"] == "account-menu-button" and "hidden" in menu
    for part in ("account-avatar", "account-email"):
        assert "account-menu-button" in BY_ID[part]["inside"], part
    assert BY_ID["account-avatar"]["aria-hidden"] == "true", "The initial is decoration; the button has a name"
    # What is in the menu, in order: the address, then what an account can do, Sign out last.
    inside = [node for node in TREE.tags if "account-menu" in node["inside"]]
    items = [node for node in inside if node.get("role") == "menuitem"]
    assert [item["id"] for item in items] == ["account-manage", "account-keys", "account-console", "account-exit"]
    assert [item["data-i18n"] for item in items] == ["account_settings_item", "account_keys", "account_console", "account_exit"]
    assert [item["tag"] for item in items] == ["button", "button", "a", "button"]
    assert "hidden" in BY_ID["account-console"] and BY_ID["account-console"]["href"] == "/admin"
    assert "account-menu" in BY_ID["account-menu-email"]["inside"], "The whole address is in the menu"
    assert BY_ID["account-badge"]["class"] == "account-menu" and "hidden" in BY_ID["account-badge"]
    # The one-line badge with its underlined links is gone.
    assert "byok-badge--account" not in INDEX and "byok-badge--account" not in CSS
    assert "#account-manage" not in CSS and ".byok-badge #account-keys" not in CSS


def test_every_target_in_it_is_at_least_44_pixels_tall():
    assert "min-height: 44px" in rule(".account-menu__button")
    assert "width: 100%" in rule(".account-menu__button")
    assert "min-height: 44px" in rule(".account-menu__item")
    # The button keeps one line; the menu shows the address whole.
    assert "text-overflow: ellipsis" in rule(".account-menu__email")
    assert "overflow-wrap: anywhere" in rule(".account-menu__who strong")
    # It opens upwards, inside the rail, which clips what leaves it.
    listed = rule(".account-menu__list")
    assert "position: absolute" in listed and "bottom: calc(100%" in listed and "left: 0" in listed and "right: 0" in listed
    assert "display: none" in rule(".account-menu__list[hidden]")


def test_the_menu_and_the_panel_are_named_in_both_languages():
    for key in ("account_menu_label", "account_signed_in_as", "account_settings_item", "capacity_busy",
                "capacity_busy_title", "account_notify_title", "account_danger_title"):
        english, chinese = strings(key)
        assert english and CJK.search(chinese) and not CJK.search(english), key
    for key in ("account_menu_label",):
        for said in strings(key):
            assert "{email}" in said
    assert "    account_manage:" not in STRINGS, "The old link's word is not kept for nothing"
    # The name the button goes by is painted from the strings, at sign-in and on a change of language.
    paint = APP.split("function paintAccountIdentity() {", 1)[1].split("\n}\n", 1)[0]
    assert 'accountMenuButton.setAttribute("aria-label", t("account_menu_label").replace("{email}", () => email));' in paint
    assert APP.count("paintAccountIdentity();") == 2


def test_the_shortcut_hint_shows_only_where_there_is_a_keyboard():
    kbd = re.search(r'<kbd class="kbd">N</kbd>', INDEX)
    assert kbd, "The hint is still in the markup, for the screens that have the key"
    hidden = CSS.index(".kbd { display: none; }")
    shown = re.search(r"@media \(hover: hover\) and \(pointer: fine\) \{\s*\.kbd \{ display: inline-block; \}\s*\}", CSS)
    assert shown and hidden < shown.start(), "Hidden first, shown where a pointer hovers"
    assert "display" not in rule(".kbd").replace("display: none;", ""), "No later rule shows it everywhere again"


def test_the_slots_line_starts_hidden():
    capacity = BY_ID["capacity"]
    assert "hidden" in capacity, "Shown by the script, to an administrator or when every slot is taken"
    assert "display: none" in rule(".capacity[hidden], .capacity__dots[hidden]")


def test_the_account_panel_has_three_parts_and_deleting_is_last_and_apart():
    panel = [node for node in TREE.tags if "account-settings" in node["inside"]]
    parts = [node for node in panel if node["tag"] == "section"]
    assert [part.get("id") or part["aria-labelledby"] for part in parts] == [
        "settings-notify-row", "settings-password-title", "settings-danger-title"]
    assert [part["class"] for part in parts] == ["gate__part", "gate__part", "gate__part gate__part--danger"]
    headings = [node for node in panel if node["tag"] == "h3"]
    assert [heading["data-i18n"] for heading in headings] == ["account_notify_title", "account_password_title",
                                                             "account_danger_title"]
    for part, heading in zip(parts, headings, strict=True):
        assert part["aria-labelledby"] == heading["id"]
    assert "hidden" in parts[0], "The notice part is shown only where the deployment sends mail"
    # Close is at the top, beside the title, which is what takes focus.
    title, close = BY_ID["account-settings-title"], BY_ID["settings-close"]
    assert title["tag"] == "h2" and title["tabindex"] == "-1"
    order = [node.get("id") for node in panel if node.get("id")]
    assert order.index("settings-close") < order.index("settings-notify-row") < order.index("settings-password-form") \
        < order.index("settings-delete-form")
    assert order[-1] == "settings-delete-submit", "Nothing comes after deleting the account"
    assert close["tag"] == "button" and close["type"] == "button"
    # No field asks for focus, and the script gives it to the heading.
    for node in panel:
        assert "autofocus" not in node, node.get("id")
    opened = APP.split("function showAccountSettings() {", 1)[1].split("const close = ", 1)[0]
    assert '$("#account-settings-title").focus();' in opened and "password\").focus()" not in opened
    # Changing the password is one thing the panel does, not the thing: its button is not the primary one.
    assert BY_ID["settings-password-submit"]["class"] == "btn btn--secondary"
    assert BY_ID["settings-delete-submit"]["class"] == "btn gate__danger"
    assert "settings-danger-title" in BY_ID["settings-delete-form"]["inside"] or \
        BY_ID["settings-delete-form"]["inside"][-1] == "account-settings"
    danger = rule(".gate__part--danger")
    assert "border: 1px solid var(--danger-border)" in danger
    assert "primary" not in " ".join(node.get("class", "") for node in panel)
