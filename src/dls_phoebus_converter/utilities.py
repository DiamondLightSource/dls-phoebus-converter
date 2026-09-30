"""Helper functions for non specific conversion use"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from lxml import etree

logger = logging.getLogger("dls_phoebus_converter")


def find_filepaths(
    bob_data: etree._ElementTree, include_symbols: bool = False
) -> Iterator[tuple[etree._Element, Path]]:
    """Yield each filepath referenced by a screen, with the element holding it.

    Different widgets hold filepaths in different tags, so several are searched.

    Args:
        bob_data: The screen to search.
        include_symbols: Include symbol widget image paths.

    Yields:
        Each element whose text is a filepath, and that filepath.
    """

    for widget in bob_data.findall(".//widget"):
        candidates: list[etree._Element | None] = []
        if include_symbols:
            candidates += widget.findall("symbols/symbol")
        candidates += [widget.find(tag) for tag in ("file", "opi_file", "image_file")]
        for action in widget.findall("actions/action"):
            # An action's file is only used when it has no path
            path_el = action.find("path")
            has_path = path_el is not None and path_el.text is not None
            candidates.append(path_el if has_path else action.find("file"))

        for element in candidates:
            if element is not None and element.text is not None:
                yield element, Path(element.text)
