import logging
from pathlib import Path

from lxml import etree

from dls_phoebus_converter.opi_converter import OpiConverter

logger = logging.getLogger("dls_phoebus_converter")


def replace_visible_script(oc: OpiConverter) -> None:
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


def remove_fe_temp_indicator_script(oc: OpiConverter) -> None:
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


def resize_absb_temps_fe22b(oc: OpiConverter) -> None:
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


def replace_progress_bar_with_linear_meter(
    bob_file_data: etree.ElementTree, dst_filepath: Path
) -> None:
    """
    HLA-1077: This replaces the progress bars in FE22B with linear meters
    to support alarm limits, which are not a feature of progress bars in Phoebus.
    """
    logger.info(
        f"Special case: Replacing ProgressBar with LinearMeter in {dst_filepath}"
    )

    def create_linear_meter_from_progress_bar(
        progress_bar: etree.Element,
    ) -> etree.Element:
        linear_meter = etree.Element("widget", type="linearmeter", version="3.0.0")

        # Inherited from progress bar widget
        etree.SubElement(linear_meter, "x").text = progress_bar.findtext("x")
        etree.SubElement(linear_meter, "y").text = progress_bar.findtext("y")
        etree.SubElement(linear_meter, "width").text = progress_bar.findtext("width")
        etree.SubElement(linear_meter, "height").text = progress_bar.findtext("height")
        etree.SubElement(linear_meter, "pv_name").text = progress_bar.findtext(
            "pv_name"
        )
        etree.SubElement(linear_meter, "actions").text = progress_bar.findtext(
            "actions"
        )

        # Additional linear meter properties
        etree.SubElement(linear_meter, "name").text = "linear meter"
        etree.SubElement(linear_meter, "display_mode").text = "1"  # BAR
        etree.SubElement(linear_meter, "show_units").text = "false"
        etree.SubElement(linear_meter, "scale_visible").text = "false"
        etree.SubElement(linear_meter, "border_alarm_sensitive").text = "false"
        etree.SubElement(linear_meter, "limits_from_pv").text = "3"  # No limits from PV
        etree.SubElement(linear_meter, "level_lolo").text = "0"
        etree.SubElement(linear_meter, "level_low").text = "0"

        # Colours
        colors = etree.SubElement(linear_meter, "colors")
        nsc = etree.SubElement(colors, "normal_status_color")
        etree.SubElement(nsc, "color", red="210", green="210", blue="210", alpha="50")
        mwc = etree.SubElement(colors, "major_warning_color")
        etree.SubElement(mwc, "color", red="255", green="0", blue="0", alpha="30")
        etree.SubElement(colors, "is_gradient_enabled").text = "true"
        etree.SubElement(
            colors, "is_highlighting_of_active_regions_enabled"
        ).text = "false"

        # Scripts
        scripts = etree.SubElement(linear_meter, "scripts")
        script = etree.SubElement(scripts, "script", file="EmbeddedPy")
        file_path = Path.joinpath(
            Path(__file__).parent,
            "../../config/scripts_to_embed/linear_meter_alarm_levels.py",
        )
        with open(file_path) as f:
            script_text = f.read()
            etree.SubElement(script, "text").text = etree.CDATA(script_text)
        etree.SubElement(script, "pv_name").text = "$(pv_name)"
        etree.SubElement(script, "pv_name").text = "$(pv_name):GETCALC"
        etree.SubElement(script, "pv_name").text = "$(pv_name):HIGH"

        return linear_meter

    for progress_bar in bob_file_data.findall(".//widget[@type='progressbar']"):
        new_linear_meter = create_linear_meter_from_progress_bar(progress_bar)
        progress_bar.getparent().replace(progress_bar, new_linear_meter)

        # Turn off alarm borders for the corresponding text update widget
        expected_text_update_widget_name = progress_bar.findtext("name") + " Label"
        for text_update in bob_file_data.findall(".//widget[@type='textupdate']"):
            if text_update.findtext("name") == expected_text_update_widget_name:
                etree.SubElement(text_update, "border_alarm_sensitive").text = "false"


# Generic function to be inlcluded in each domain-specific special case module.
# This is dynamically imported and then called by the main conversion process.
def run(oc: OpiConverter) -> None:
    """Make any case-by-case adjustments to FE specific screens which are not handled
    by the normal conversion process."""

    if "absb_temps_fe22b.bob" in str(oc.dst_filepath):
        resize_absb_temps_fe22b(oc)
        replace_progress_bar_with_linear_meter(oc.bob_data, oc.dst_filepath)

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
