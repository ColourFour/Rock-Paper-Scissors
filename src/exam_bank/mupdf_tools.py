from __future__ import annotations

from typing import Any


def quiet_mupdf(fitz: Any) -> None:
    """Suppress MuPDF's C-level warning/error printing.

    MuPDF sometimes reports recoverable PDF structure-tree issues directly to
    stderr, outside Python's warnings/logging system. The files can still be
    read and rendered, so keep terminal output clean while allowing extraction
    exceptions to propagate normally.
    """

    tools = getattr(fitz, "TOOLS", None)
    if tools is None:
        return
    for method_name in ["mupdf_display_warnings", "mupdf_display_errors"]:
        method = getattr(tools, method_name, None)
        if method is None:
            continue
        try:
            method(False)
        except Exception:
            continue
