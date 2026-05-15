import logging

from lxml import etree

from dls_phoebus_converter.opi_converter import OpiConverter

logger = logging.getLogger("dls_phoebus_converter")


def replace_visible_script(oc: OpiConverter):
    """Replace this complex script with a rule"""

    logger.info(
        f"Special case: Removing references to visible.py from {oc.dst_filepath}"
    )

    # Find and remove all <script> elements which use visible.py. Replace it with a new
    # rule
    for script in oc.bob_data.findall('.//script[@file="visible.py"]'):
        parent = script.getparent()
        if parent is not None:
            parent.remove(script)
            widget = parent.getparent()
            if widget is not None:
                rules_found = False
                for child in widget:
                    if child.tag == "rules":
                        rule_xml = (
                            '<rule name="set_visible" prop_id="visible" '
                            'out_exp="false"><exp bool_exp="pv0==4">'
                            "<value>true</value></exp><exp "
                            'bool_exp="pv0==5"><value>true</value></exp>'
                            '<exp bool_exp="pv0==6"><value>true</value>'
                            '</exp><exp bool_exp="pv0==7"><value>true'
                            '</value></exp><exp bool_exp="true">'
                            "<value>false</value></exp><pv_name>"
                            "$(motor):ELOSS</pv_name></rule>"
                        )
                        child.insert(-1, etree.fromstring(rule_xml))
                        rules_found = True
                        continue
                if not rules_found:
                    rules_xml = (
                        '<rules><rule name="set_visible" prop_id="visible" '
                        'out_exp="false"><exp bool_exp="pv0==4"><value>true'
                        '</value></exp><exp bool_exp="pv0==5"><value>true'
                        '</value></exp><exp bool_exp="pv0==6"><value>true'
                        '</value></exp><exp bool_exp="pv0==7"><value>true'
                        '</value></exp><exp bool_exp="true"><value>false'
                        "</value></exp><pv_name>$(motor):ELOSS</pv_name>"
                        "</rule></rules>"
                    )
                    widget.insert(-1, etree.fromstring(rules_xml))


def remove_fe_temp_indicator_script(oc: OpiConverter):
    """This script was being used to colour ProgressBars based on hihi and hi values.
    Instead we now just use an alarm border which changes the border based on alarm.
    Assuming hihi and hi are configured to generate Major and Minor alarms, the
    behaviour is the same, and so we dont need this old rule which is broken in Phoebus
    anyway"""

    logger.info(
        "Special case: Removing references to feTempIndicator.py from "
        f"{oc.dst_filepath}"
    )

    # Find and remove all <script> elements which use feTempIndicator.py
    for script in oc.bob_data.findall('.//script[@file="feTempIndicator.py"]'):
        parent = script.getparent()
        if parent is not None:
            parent.remove(script)

    for script in oc.bob_data.findall(
        './/script[@file="common/plc/feTempIndicator.py"]'
    ):
        parent = script.getparent()
        if parent is not None:
            parent.remove(script)


def resize_absb_temps_fe22b(oc: OpiConverter):
    """
    HLA-1061: This is a special case for FE22B where the size of the screen does not
    properly encompass the widgets within it. This results in the screen being cut off
    when embedded via a linking container, so we manually fix it here.
    """
    logger.info(f"Special case: Resizing screen for {oc.dst_filepath}")

    new_height = 120
    new_width = 400

    oc.bob_data.getroot().find("height").text = str(new_height)
    oc.bob_data.getroot().find("width").text = str(new_width)


# Generic function to be inlcluded in each domain-specific special case module.
# This is dynamically imported and then called by the main conversion process.
def run(oc: OpiConverter):
    """Make any case-by-case adjustments to FE specific screens which are not handled
    by the normal conversion process."""

    if "absb_temps_fe22b.bob" in str(oc.dst_filepath):
        resize_absb_temps_fe22b(oc)

    for name in [
        "FE24B.bob",
        "absb_pbpm_temps.bob",
        "absb_temps_fe22b.bob",
        "absb_temps.bob",
        "absb.bob",
    ]:
        if name in str(oc.dst_filepath):
            remove_fe_temp_indicator_script(oc)

    if "motor.bob" in str(oc.dst_filepath):
        replace_visible_script(oc)
