"""Extra conversion steps which arent handled by the phoebus converter"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lxml import etree
from lxml.etree import Element

from dls_phoebus_converter.macros import handle_macros
from dls_phoebus_converter.widget_fixes import fix_widget_issues

if TYPE_CHECKING:
    from dls_phoebus_converter.opi_converter import OpiConverter
    from dls_phoebus_converter.screen_converter import ScreenConverter

from dls_phoebus_converter.support_modules import (
    find_required_support_modules,
    update_filepaths,
)

logger = logging.getLogger("dls_phoebus_converter")

# These are the default sizes used in the Diamond setup that are
# used when a screen does not define a height or width.
DEFAULT_SCREEN_WIDTH = 800  # px
DEFAULT_SCREEN_HEIGHT = 600  # px


def post_conversion_steps(sc: ScreenConverter, oc: OpiConverter):
    # If sc is None, then we are just converting a single_file, so we dont
    # do any of the changes for converting a technical area.
    if sc is not None:
        find_required_support_modules(sc, oc)

    fix_widget_issues(sc, oc)
    expand_screen_to_widgets(oc.bob_data)

    if sc is not None:
        handle_macros(oc.bob_data, oc.macros)
        update_filepaths(sc, oc)

    # Catch any conversion we may have missed, also used when converting a single
    # opi file.
    for el in oc.bob_data.getroot().iter():
        if el.text is not None and ".opi" in el.text:
            el.text = el.text.replace(".opi", ".bob")
            oc.completed_conversion_steps.replace_opi_ext = True

    # Special cases are tweaks which are not handled by the
    # normal conversion process and are often unique to a specific screen.
    # These are optionally defined in a domain-specific special case module.
    if sc is not None and sc.special_case_module is not None:
        sc.special_case_module.run(oc)


def expand_screen_to_widgets(bob_data: etree.ElementTree) -> None:
    """Resize the screen to fit the widgets on it. This is useful for screens which have
    been converted from CS-Studio where the screen size was not set correctly."""

    max_width = 0
    max_height = 0

    # padding is applied to account for factors outside of the height/width properties
    # of a widget, such as border width and buttons expanding when highlighted.
    padding = 5  # px

    for widget in bob_data.findall(".//widget"):
        x = get_dimension(widget, "x")
        y = get_dimension(widget, "y")
        width = get_dimension(widget, "width")
        height = get_dimension(widget, "height")

        max_width = max(max_width, x + width)
        max_height = max(max_height, y + height)

    root = bob_data.getroot()
    screen_width = get_dimension(root, "width", DEFAULT_SCREEN_WIDTH)
    screen_height = get_dimension(root, "height", DEFAULT_SCREEN_HEIGHT)

    new_width = max_width + padding
    new_height = max_height + padding

    # Only update the display dimensions if they are
    # too small to show all of the widgets
    if screen_width < max_width:
        width_el = root.find("width")
        if width_el is None:
            width_el = etree.SubElement(root, "width")
        width_el.text = str(new_width)
        logger.info(f"Display width resized to: {new_width}")

    if screen_height < max_height:
        height_el = root.find("height")
        if height_el is None:
            height_el = etree.SubElement(root, "height")
        height_el.text = str(new_height)
        logger.info(f"Display height resized to: {new_height}")


def get_dimension(element: Element, name: str, default: int = 0) -> int:
    """Read an integer dimension, falling back to a default where it is not set.

    Args:
        element: The widget or display to read from.
        name: The dimension property, such as "x" or "width".
        default: Used when the property is absent.

    Returns:
        The dimension in pixels.
    """

    value = element.findtext(name)
    return default if value is None else int(value)
