import logging

import xmltodict

logger = logging.getLogger("dls_phoebus_converter")


def resize_absb_temps_fe22b(bob_file, conversion):
    """
    HLA-1061: This is a special case for FE22B where the size of the screen does not properly
    encompass the widgets within it. This results in the screen being cut off when
    embedded via a linking container, so we manually fix it here.
    """
    logger.info(f"Special case: Resizing screen for {bob_file}")

    new_height = 120
    new_width = 400

    conversion.all_phoebus_data["display"]["height"] = new_height
    conversion.all_phoebus_data["display"]["width"] = new_width


# Generic function to be inlcluded in each domain-specific special case module.
# This is dynamically imported and then called by the main conversion process.
def run(bob_file, conversion):
    """Make any case-by-case adjustments to FE specific screens which are not handled
    by the normal conversion process."""

    if "absb_temps_fe22b.bob" in str(bob_file):
        resize_absb_temps_fe22b(bob_file, conversion)
