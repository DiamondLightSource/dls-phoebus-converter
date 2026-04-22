import logging

import xmltodict

try:
    logger = logging.getLogger("dls_phoebus_converter")
except NameError:
    print("Logger not found: dls_phoebus_converter")


def resize_absb_temps_fe22b(bob_file, conversion):
    """
    HLA-1061: This is a special case for FE22B where the size of the screen does not properly
    encompass the widgets within it. This results in the screen being cut off when
    embedded via a linking container, so we manually fix it here.
    """
    logger.info(f"Resizing screen for {bob_file}")

    new_height = 120
    new_width = 400

    conversion.all_phoebus_data["display"]["height"] = new_height
    conversion.all_phoebus_data["display"]["width"] = new_width
