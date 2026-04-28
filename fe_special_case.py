import logging
import lxml.etree as ET
import xmltodict
import re

logger = logging.getLogger("dls_phoebus_converter")


def remove_feTempIndicator_script(bob_file, conversion):
    """This script was being used to colour ProgressBars based on hihi and hi values.
    Instead we now just use an alarm border which changes the border based on alarm.
    Assuming hihi and hi are configured to generate Major and Minor alarms, the behaviour
    is the same, and so we dont need this old rule which is broken in Phoebus anyway"""
    
    logger.info(f"Special case: Removing references to feTempIndicator.py from {bob_file}")

    xml = xmltodict.unparse(conversion.all_phoebus_data)
    xml_stripped = re.sub(r'<\?xml[^?]*\?>', '', xml)
     # Parse the XML file
    root = ET.fromstring(xml_stripped)
    
    # Find and remove all <script> elements which use feTempIndicator.py
    for script in root.findall('.//script[@file="feTempIndicator.py"]'):
        parent = script.getparent()
        if parent is not None:
            parent.remove(script)
    
    for script in root.findall('.//script[@file="common/plc/feTempIndicator.py"]'):
        parent = script.getparent()
        if parent is not None:
            parent.remove(script)

    # Write the modified XML back to our dict
    as_dict = xmltodict.parse(ET.tostring(root))
    conversion.all_phoebus_data = as_dict
    if "widget" in as_dict["display"]:
        conversion.widget_data = as_dict["display"]["widget"]


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

    for name in ["FE24B.bob", "absb_pbpm_temps.bob", "absb_temps_fe22b.bob", "absb_temps.bob", "absb.bob"]:
        if name in str(bob_file):
            remove_feTempIndicator_script(bob_file, conversion)