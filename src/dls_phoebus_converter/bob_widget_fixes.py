"""Fix, by widget type, the widgets in a .bob converted by Phoebus."""

from __future__ import annotations

import copy
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree
from lxml.etree import Element

from dls_phoebus_converter.symbol_widgets import fix_edm_symbol_widgets

if TYPE_CHECKING:
    from dls_phoebus_converter.opi_converter import CompletedSteps, OpiConverter
    from dls_phoebus_converter.screen_converter import ScreenConverter

logger = logging.getLogger("dls_phoebus_converter")


def fix_bob_widgets(sc: ScreenConverter, oc: OpiConverter):
    steps = oc.completed_conversion_steps
    for widget in oc.bob_data.findall(".//widget"):
        if "typeId" in widget.attrib:
            logger.error(
                f"The Phoebus converter did not convert widget "
                f"{widget.attrib['typeId']} in {oc.src_file_path}. Widgets after it "
                f"are not fixed."
            )
            # Returning here leaves every later widget in the file unfixed. Correcting
            # it changes the converted output, so it is left as it is for now.
            return

        widget_type = widget.attrib.get("type")
        if widget_type == "action_button":
            actions = widget.find("actions")
            if actions is not None:
                text = widget.find("text")
                if text is not None:
                    if text.text in ("EXIT", "Exit", "Cancel"):
                        # We are assuming that there is only one action on this widget
                        # and so only update the first one we find.
                        fix_exit_button(steps, actions.find("action"))
                    fix_widget_actions(steps, oc.src_file_path, actions)

        elif widget_type == "symbol":
            for child in widget:
                if child.tag == "actions":
                    fix_widget_actions(
                        steps, oc.src_file_path, widget.find(".//actions")
                    )
            if sc is not None:
                fix_edm_symbol_widgets(sc, oc, widget)

        elif widget_type == "progressbar":
            # Actions are not supported on progressBars in Phoebus, so
            # we instead layer a transparent action button on top.
            for child in widget:
                if child.tag == "actions":
                    move_action_to_transparent_button(widget)
            # Look for any progress bar widgets with alarm borders enabled
            alarm_sensitive_progress_bars = get_alarm_sensitive_progress_bars(
                oc.const_opi_data
            )
            name = widget.find("name")
            pv_name = widget.find("pv_name")
            if name is not None and pv_name is not None:
                if [name.text, pv_name.text] in alarm_sensitive_progress_bars:
                    border = widget.find("border_alarm_sensitive")
                    if border is None:
                        border = etree.SubElement(widget, "border_alarm_sensitive")
                    border.text = "true"

        elif widget_type == "tank":
            # Phoebus is missing the <transparent_background> option, so we just set the
            # background colour to transparent
            transparent_tank_backgrounds = get_transparent_background_tank_widgets(
                oc.const_opi_data
            )
            name = widget.find("name")
            pv_name = widget.find("pv_name")
            if name is not None and pv_name is not None:
                if [name.text, pv_name.text] in transparent_tank_backgrounds:
                    new_el = etree.fromstring(
                        "<background_color>\n<color name='Transparent' red='255' green='255' blue='255'></color>\n</background_color>\n"  # noqa: E501
                    )
                    old_el = widget.find("background_color")
                    if old_el is None:
                        widget.append(new_el)
                    else:
                        widget.replace(old_el, new_el)
        convert_pv_function(widget)
        fix_rule_expressions(steps, widget)
        fix_actions_on_widgets_without_actions_functionality(steps, widget)


def fix_exit_button(steps: CompletedSteps, action: Element):
    steps.fix_exit_but = True
    action.attrib["type"] = "close_display"
    action.attrib["description"] = "Close display"
    description = action.find("description")
    if description is not None:
        description.text = "Close display"

    old_script = action.find("script")
    if old_script is not None:
        action.remove(old_script)


def fix_widget_actions(steps: CompletedSteps, src_file_path: Path, actions: Element):
    """Fix issues with widget actions"""

    for action in actions:
        fix_action_open_macro(steps, action)
        replace_open_in_tab(steps, action)
        fix_open_databrowser_actions(steps, src_file_path, action)


def fix_action_open_macro(steps: CompletedSteps, action: Element):
    """Replace the macro $(name) with the actions parent widgets name"""

    if action.attrib["type"] == "open_display":
        for macros_el in action.findall("macros"):
            for macro in macros_el:
                if macro.text == "$(name)":
                    steps.fix_action_macro_name = True
                    macro.text = action.getparent().getparent().find("name").text


def replace_open_in_tab(steps: CompletedSteps, action: Element):
    if action.attrib["type"] == "open_display":
        for target in action.findall("target"):
            if target.text == "tab":
                target.text = "standalone"
                steps.replace_action_tab = True


def fix_open_databrowser_actions(
    steps: CompletedSteps, src_file_path: Path, action: Element
):
    """Fix custom scripts/commands used to launch the databrowser which dont work
    in Phoebus"""

    if action.attrib["type"] == "execute":
        script_text_el = action.find("script/text")
        if "executeEclipseCommand" in script_text_el.text:
            if "org.csstudio.trends.databrowser2" in script_text_el.text:
                search_string = script_text_el.text
                if match := re.search(r"'pvnames',\s*'([^']+)'", search_string):
                    pv_names = match.group(1)
                    pv_names = pv_names.split(",")
                    switch_to_new_databrowser_action(action, pv_names)
                    steps.replace_db_script = True
                else:
                    logger.error(
                        "Could not find any PV names to add to the open_data_browser"
                        f"action when converting the script: {search_string}"
                    )

            else:
                logger.warning(
                    "Screen contains an executeEclipseCommand script which is"
                    "not supported by Phoebus. Found script: "
                    f"{script_text_el.text} in file {src_file_path}"
                )

    elif action.attrib["type"] == "command":
        command = action.find("command").text
        if "strip.py" in command or "strip.sh" in command:
            str_list = command.split(" ")
            pv_names = []
            for i, string in enumerate(str_list):
                if "strip.py" in string or "strip.sh" in string:
                    pv_names.extend(str_list[i + 1 : -1])
                    break
            switch_to_new_databrowser_action(action, pv_names)
            steps.replace_db_script = True


def switch_to_new_databrowser_action(action: Element, pv_names: list[str]):
    """Remove the old action and replace with the new open_data_browser action."""

    new_action = Element("action", type="open_data_browser")
    etree.SubElement(new_action, "description").text = "Open Data Browser"
    etree.SubElement(new_action, "pv_name").text = " ".join(pv_names)
    etree.SubElement(new_action, "timeframe").text = "1 hour"

    actions = action.getparent()
    # Add the new action
    actions.append(new_action)
    # Delete the old action
    actions.remove(action)


def move_action_to_transparent_button(widget: Element):
    """Move the action on the target widget to a transparent button and place over the
    base widget.

    Widgets in Phoebus sometimes do not support actions being attached to them
    where CS-Studio did. Additionally, not all actions in phoebus can be triggered by
    a left click. In these cases, we move the action to a transparent action button
    and layer it on top of the original widget"""

    def create_action_button_from_widget(widget: Element) -> Element:
        action_button = Element("widget", type="action_button", version="3.0.0")
        etree.SubElement(action_button, "name").text = "PB Action Button"
        etree.SubElement(action_button, "text").text = ""
        etree.SubElement(action_button, "transparent").text = "true"

        # Inherited from widget.
        etree.SubElement(action_button, "width").text = widget.findtext("width")
        etree.SubElement(action_button, "height").text = widget.findtext("height")
        # Sometimes x and y are not defined in the .bob file and will default to 0.
        etree.SubElement(action_button, "x").text = widget.findtext("x", "0")
        etree.SubElement(action_button, "y").text = widget.findtext("y", "0")

        return action_button

    # Inject the actions.
    new_action_button = create_action_button_from_widget(widget)
    action_sub_element = etree.SubElement(new_action_button, "actions")
    widget_actions = widget.find("./actions")

    for action in widget_actions:
        new_action = copy.deepcopy(action)
        action_sub_element.append(new_action)

    # Placing the action button at the end of the file ensures
    # it is layered on top of the original widget
    widget.getparent().append(new_action_button)
    widget.remove(widget_actions)


def get_alarm_sensitive_progress_bars(opi_data: etree.ElementTree):
    """Get a list of identifying string pairs which are used to identify an
    alarm sensitive progressbar."""

    # A progressbar is alarm sensitive if any of these are set
    alarm_properties = (
        "backcolor_alarm_sensitive",
        "forecolor_alarm_sensitive",
        "fillcolor_alarm_sensitive",
    )

    alarm_sensitive_progress_bars = []
    xpath = ".//widget[@typeId='org.csstudio.opibuilder.widgets.progressbar']"
    for widget in opi_data.findall(xpath):
        if any(widget.findtext(prop) == "true" for prop in alarm_properties):
            name_ids = [widget.find("name").text, widget.find("pv_name").text]
            alarm_sensitive_progress_bars.append(name_ids)

    return alarm_sensitive_progress_bars


def get_transparent_background_tank_widgets(opi_data: etree.ElementTree):
    """Get a list of identifying string pairs which are used to identify a
    tank widget with a transparent background."""

    transparent_backgrounds = []
    xpath = ".//widget[@typeId='org.csstudio.opibuilder.widgets.tank']"
    for widget in opi_data.findall(xpath):
        if widget.findtext("transparent_background") == "true":
            name_ids = [widget.find("name").text, widget.find("pv_name").text]
            transparent_backgrounds.append(name_ids)

    return transparent_backgrounds


def convert_pv_function(widget: Element):
    for child in widget.iter():
        inp_string = child.text
        if inp_string is not None and "pv(" in inp_string:
            # cs-studio writes a PV name as pv("NAME"), Phoebus as `NAME`
            pv_replacement = re.sub(r'pv\("(.*?)"\)', r"`\1`", inp_string)
            # Anything still holding pv( did not match, either a nested call such as
            # pv(concat(...)) or an unclosed pv(". Phoebus has no equivalent for the
            # former, so warn and leave the formula as it was.
            if "pv(" in pv_replacement:
                logger.warning(
                    f"Cannot fix the following formula in Phoebus {inp_string}"
                )
            else:
                logger.info(f"Replace pv() function with {pv_replacement}")
                child.text = pv_replacement


def fix_rule_expressions(steps: CompletedSteps, widget: Element):
    """Fix common issues that come up in cs-studio rules"""

    expressions = widget.findall("rules/rule/exp")
    for exp in expressions:
        # Use new syntax for getting a PV alarm severity
        fix_pv_severity_expression(steps, exp)

        # widget.getValue() is not available in Phoebus, we assume this is an attempt to
        # get the value of the widgets pv, so we replace it with pv0
        if "widget.getValue()" in exp.attrib["bool_exp"]:
            exp.attrib["bool_exp"] = exp.attrib["bool_exp"].replace(
                "widget.getValue()", "pv0"
            )


def fix_pv_severity_expression(steps: CompletedSteps, exp_el: Element):
    # OK, Major, Minor, Invalid/undefined
    css_sev_expressions = [
        "pvLegacySev0==0",
        "pvLegacySev0==1",
        "pvLegacySev0==2",
        "pvLegacySev0==-1",
    ]
    phoebus_sev_expressions = ["pvSev0==0", "pvSev0==2", "pvSev0==1", "pvSev0==3"]
    initial_attrib = exp_el.attrib["bool_exp"]
    modified_attrib = initial_attrib

    for css_exp, phoebus_exp in zip(
        css_sev_expressions, phoebus_sev_expressions, strict=True
    ):
        if css_exp in initial_attrib:
            steps.update_leg_sev = True
            modified_attrib = initial_attrib.replace(css_exp, phoebus_exp)
            logger.debug(f"Fixing {css_exp} to {phoebus_exp} in rule")

    exp_el.attrib["bool_exp"] = modified_attrib


def fix_actions_on_widgets_without_actions_functionality(
    steps: CompletedSteps, widget: Element
):
    """Some widgets which could have actions in CS-Studio, cannot have actions in
    Phoebus. We look for these situations and try to fix them by converting the widget
    to an action button which can have actions."""

    first_action = widget.find("actions/action")
    if first_action is None:
        return

    widget_type = widget.attrib["type"]
    if widget_type in ("action_button", "symbol"):
        return

    steps.non_ab_action = True
    logger.debug(
        "Action contained in widget that isn't an action button: "
        f"{widget_type}, name: {widget.find('name').text}"
    )
    logger.debug(f"    action: {first_action.text}")

    if widget_type not in ("rectangle", "bool_button"):
        return

    if widget_type == "bool_button" and (
        widget.find("on_label").text != widget.find("off_label").text
    ):
        return

    steps.replace_with_ab = True
    logger.debug("    Attempting to fix by converting to an action_button")
    widget.attrib["type"] = "action_button"

    text = widget.find("text")
    if text is None:
        text = etree.SubElement(widget, "text")
    text.text = widget.findtext("off_label", "")

    for rule in widget.findall("rules/rule"):
        if rule.attrib["prop_id"] == "line_color":
            rule.getparent().remove(rule)
