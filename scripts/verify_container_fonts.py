"""Fail the image build if CJK PDF export would silently degrade.

_resolve_font() falls back to Helvetica when no CJK font is found, so a missing
font package produces a PDF full of blank boxes rather than an error — the
failure only becomes visible to whoever opens the report. Debian moves these
files between releases (opentype/noto, noto-cjk, google-noto-cjk are all real
paths across versions), so pinning one path in the Dockerfile is not enough:
this asserts that whatever the package installed is actually reachable.

Run during the build, not at startup, so a bad image never ships.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui.pdf_export as pdf_export  # noqa: E402

# Languages whose reports cannot be rendered by the Latin fallback.
_CJK_LANGUAGES = ("Simplified Chinese", "Traditional Chinese", "Japanese", "Korean")


def main() -> int:
    failures: list[str] = []
    # Looked up on the module at call time rather than bound at import, so the
    # tests can substitute a resolver and exercise the failure paths.
    for language in _CJK_LANGUAGES:
        try:
            resolved = pdf_export._resolve_font(language)
        except Exception as exc:  # noqa: BLE001 - report, do not mask
            failures.append(f"  {language}: raised {type(exc).__name__}: {exc}")
            continue
        if resolved != pdf_export._EMBEDDED_FONT_NAME:
            failures.append(f"  {language}: resolved to {resolved!r}, expected an embedded font")
        else:
            print(f"  ok  {language}")

    if failures:
        print("\nCJK font verification failed:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        print(
            "\nNote that a CID font name here is still a failure. The fallback "
            "chain degrades to CID fonts (STSong-Light and similar) before it "
            "reaches Helvetica, and those rely on the reader having the "
            "typeface installed — which does not hold for a PDF generated on a "
            "server and downloaded by someone else.\n"
            "Check that fonts-noto-cjk installed and that the path it wrote "
            "appears in _CJK_TTF_CANDIDATES (ui/pdf_export.py).",
            file=sys.stderr,
        )
        return 1

    print("CJK fonts verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
