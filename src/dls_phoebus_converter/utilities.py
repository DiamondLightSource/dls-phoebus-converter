"""Helper functions for non specific conversion use"""

from __future__ import annotations

import logging
import typing
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dls_phoebus_converter.screen_converter import ScreenConverter


logger = logging.getLogger("dls_phoebus_converter")


def search_widget_filepaths(
    sc: ScreenConverter,
    widget,
    func: typing.Callable,
    widget_file_paths=None,
    macros=None,
):
    """This generic function takes a widget and searches for any references to
    filepaths. Filepaths are used in different ways for different widgets and so
    there are serveral tpyes of filepath tag that we search for. When a filepath is
    found, it is passed into the passed func callable."""

    args = [arg for arg in [widget_file_paths, macros] if arg is not None]

    for symbol_widget in widget.findall("symbols/symbol"):
        if symbol_widget.text is not None:
            # We only log when we find an edm widget not when we later
            # switch it
            if func.__name__ == "append_new_filepath":
                logger.warning(
                    "Warning, edm style symbol widget detected: "
                    f"{widget.find('name').text}"
                )
            if func(sc, Path(symbol_widget.text), *args, symbol=True):
                symbol_widget.text = func(
                    sc, Path(symbol_widget.text), *args, symbol=True
                )

    file_el = widget.find("file")
    if file_el is not None and file_el.text is not None:
        if func(sc, Path(file_el.text), *args):
            file_el.text = func(sc, Path(file_el.text), *args)

    opi_file_el = widget.find("opi_file")
    if opi_file_el is not None and opi_file_el.text is not None:
        if func(sc, Path(opi_file_el.text), *args):
            opi_file_el.text = func(sc, Path(opi_file_el.text), *args)

    image_file_el = widget.find("image_file")
    if image_file_el is not None and image_file_el.text is not None:
        if func(sc, Path(image_file_el.text), *args):
            image_file_el.text = func(sc, Path(image_file_el.text), *args)

    action_els = widget.findall("./actions/action")
    for action_el in action_els:
        path_el = action_el.find("path")
        file_el = action_el.find("file")
        if path_el is not None and path_el.text is not None:
            if func(sc, Path(path_el.text), *args):
                path_el.text = func(sc, Path(path_el.text), *args)
        elif file_el is not None and file_el.text is not None:
            if func(sc, Path(file_el.text), *args):
                file_el.text = func(sc, Path(file_el.text), *args)
