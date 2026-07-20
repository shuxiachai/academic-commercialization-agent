import sys

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

from ui.ui import demo, _CSS, _theme

if __name__ == "__main__":
    demo.launch(css=_CSS, theme=_theme)
