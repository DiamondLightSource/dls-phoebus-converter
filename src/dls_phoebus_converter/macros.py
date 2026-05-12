"""Manages the conversion of existing macros and addition of new macros"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from lxml import etree

from dls_phoebus_converter.logconfig import setup_logging

if TYPE_CHECKING:
    from dls_phoebus_converter.opi_converter import OpiConverter

MACRO_EXCEPTION_LIST = ["pv_name", "pv_value", "name", "actions"]

if not logging.getLogger("dls_phoebus_converter"):
    setup_logging()
logger = logging.getLogger("dls_phoebus_converter")


def fill_in_file_path_macros(string: str, macros) -> str:
    def replace(match):
        key = match.group(1)  # the ‘x’ inside ${x}
        return macros.get(key, match.group(0))  # default: leave unchanged

    if macros is not None:
        resolved_path = re.sub(r"\$[\{\(]([^\}\)\s]+)[\}\)]", replace, str(string))
        return resolved_path
    else:
        return string


def add_new_macros(
    oc: OpiConverter,
    macro_names: list[str],
    macro_values: list[str],
) -> None:
    """Add a list of macro name/values to the top level of the bob file."""

    if "macros" not in oc.bob_data.getroot():
        oc.bob_data.getroot().append(etree.Element("macros"))

    macro_data = oc.bob_data.find("macros")

    for new_macro_name, new_macro_value in zip(macro_names, macro_values, strict=True):
        for existing_macro_name, existing_macro_value in macro_data.items():
            if existing_macro_name == new_macro_name:
                logging.warning(
                    f"An existing file macro is being overwritten: "
                    f"{existing_macro_name}:{existing_macro_value} -> "
                    f"{new_macro_name}:{new_macro_value}"
                )
        new_macro = etree.Element(new_macro_name)
        new_macro.text = str(new_macro_value)
        macro_data.append(new_macro)


def handle_macros(oc: OpiConverter) -> None:
    """Look for unique instances of a macro eg ${string} in the bob file. We ignore
    a small number of macros which are defined from other widget fields
    (MACRO_EXCEPTION_LIST). If a macro is found in a file but has not been defined
    in the ConversionConfig, then we log a warning."""

    new_macro_names = []
    new_macro_values = []
    content = etree.tostring(oc.bob_data, encoding="unicode")
    identified_macros = re.findall(r"\$[\{\(]([^\}\)\s]+)[\}\)]", content)

    unique_identified_macros = list(dict.fromkeys(identified_macros))
    logger.info(f"Found macros in file: {unique_identified_macros}")

    for macro in unique_identified_macros:
        # Some macros refer to internal Phoebus objects, so we dont resolve these
        if macro not in MACRO_EXCEPTION_LIST:
            if macro in oc.macros.keys():
                new_macro_names.append(macro)
                new_macro_values.append(oc.macros[macro])
            else:
                # This macro has not been defined!
                logger.warning(
                    f"Could not find definition for macro: '{macro}'. "
                    "Should this have been defined in your yaml config?"
                )

    # Add macros defined in config even if they are not used in the parent display
    for m_name, m_key in oc.macros.items():
        if m_name not in new_macro_names:
            new_macro_names.append(m_name)
            new_macro_values.append(m_key)

    add_new_macros(oc, new_macro_names, new_macro_values)
