"""Conversion steps which are required before running the phoebus converter"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lxml import etree

if TYPE_CHECKING:
    from dls_phoebus_converter.opi_converter import OpiConverter


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
                oc.completed_conversion_steps.replace_edm_sym = True
    return fixed


def fix_grouping_container(oc: OpiConverter):
    """Sometimes group containers are missing border_color or border_style elements,
    if this is the case then add them with sensible defaults."""

    for widget in oc.opi_data.findall(
        ".//widget[@typeId='org.csstudio.opibuilder.widgets.groupingContainer']"
    ):
        oc.completed_conversion_steps.fix_group_cont = True
        logger.debug("Fixing missing border property in 'Group' widget")

        if widget.find("border_color") is None:
            widget.append(
                etree.fromstring(
                    '<border_color>\n<color name="Canvas" red="200" green="200" blue="200"></color>\n</border_color>\n'  # noqa: E501
                )
            )

        if widget.find("border_style") is None:
            widget.append(etree.fromstring("<border_style>0</border_style>\n"))

    return oc.completed_conversion_steps.fix_group_cont
