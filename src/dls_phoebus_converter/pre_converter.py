"""Conversion steps which are required before running the phoebus converter"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from dls_phoebus_converter.logconfig import setup_logging

if TYPE_CHECKING:
    from dls_phoebus_converter.opi_converter import OpiConverter

if not logging.getLogger("dls_phoebus_converter"):
    setup_logging()
logger = logging.getLogger("dls_phoebus_converter")


def pre_conversion_steps(oc: OpiConverter):
    use_modified_opi = False
    use_modified_opi = replace_edm_symbol_widget(oc)
    if oc.fix_group:
        # Fix missing border items from grouping container
        use_modified_opi = fix_grouping_container(oc) or use_modified_opi
    oc.write_opi_file_contents()
    return use_modified_opi


def replace_edm_symbol_widget(oc: OpiConverter):
    fixed = False
    for element in oc.opi_data.iter():
        for key, value in element.attrib.items():
            if value == "org.csstudio.opibuilder.widgets.edm.symbolwidget":
                logger.debug("Replacing CSS EDM Widgets in OPI before conversion")
                element.attrib[key] = (
                    "org.csstudio.opibuilder.widgets.symbol.multistate.MultistateMonitorWidget"
                )
                fixed = True
                oc.conversion_steps.replace_edm_sym = True
    return fixed


def fix_grouping_container(oc: OpiConverter):
    fixed = False
    check_for_border_prop = False
    found_border_prop = False
    for element in oc.opi_data.iter():
        if (
            "org.csstudio.opibuilder.widgets.groupingContainer"
            in element.attrib.values()
            and not check_for_border_prop
        ):
            check_for_border_prop = True

        elif element.tag == "widget" and "typeId" in element.attrib.keys():
            if check_for_border_prop and not found_border_prop:
                logger.debug("Fixing missing border property in 'Group' widget")
                fixed = True
                element.append(
                    '<border_color>\n<color name="Canvas" red="200" green="200" blue="200"></color>\n</border_color>\n<border_style>0</border_style>\n'  # noqa: E501
                )
                # Reset
                check_for_border_prop = False
                found_border_prop = False

        if check_for_border_prop:
            if element.tag == "border_color":
                check_for_border_prop = False
                found_border_prop = True
    return fixed
