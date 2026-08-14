"""Extra conversion steps which arent handled by the phoebus converter"""

from __future__ import annotations

import copy
import logging
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree
from lxml.etree import Element

from dls_phoebus_converter.macros import fill_in_macros, handle_macros
from dls_phoebus_converter.support_modules import ACC_UI_SUPPORT_MODULE_LIST

if TYPE_CHECKING:
    from dls_phoebus_converter.opi_converter import OpiConverter
    from dls_phoebus_converter.screen_converter import ScreenConverter

from dls_phoebus_converter.support_modules import (
    find_required_support_modules, get_existing_support_module_filepath,
    handle_support_modules)

logger = logging.getLogger("dls_phoebus_converter")

# These are the default sizes used in the Diamond setup that are
# used when a screen does not define a height or width.
DEFAULT_SCREEN_WIDTH = 800  # px
DEFAULT_SCREEN_HEIGHT = 600  # px


def post_conversion_steps(oc: OpiConverter, sc: ScreenConverter):
    # If sc is None, then we are just converting a single_file, so we dont
    # do any of the changes for converting a technical area.
    if sc is not None:
        find_required_support_modules(sc, oc)

    fix_widget_issues(oc, sc)
    expand_screen_to_widgets(oc)

    if sc is not None:
        handle_macros(oc)
        handle_support_modules(sc, oc)

    # Catch any conversion we may have missed, also used when converting a single
    # opi file.
    for el in oc.bob_data.getroot().iter():
        if el.text is not None and ".opi" in el.text:
            el.text = el.text.replace(".opi", ".bob")

    # Special cases are tweaks which are not handled by the
    # normal conversion process and are often unique to a specific screen.
    # These are optionally defined in a domain-specific special case module.
    try:
        sc.special_case_module.run(oc)
    except AttributeError:
        pass


def get_widget_dimension(widget: Element, widget_property: str) -> int:
    # Widgets without a size property defined in Phoebus are 0
    if widget.findtext(widget_property) is None:
        return 0
    else:
        return int(widget.findtext(widget_property))


def get_screen_width(display: Element) -> int:
    # screens without a width property defined in Phoebus are set to a default size
    if display.findtext("width") is None:
        return DEFAULT_SCREEN_WIDTH
    else:
        return int(display.findtext("width"))


def get_screen_height(display: Element) -> int:
    # screens without a height property defined in Phoebus are set to a default size
    if display.findtext("height") is None:
        return DEFAULT_SCREEN_HEIGHT
    else:
        return int(display.findtext("height"))


def expand_screen_to_widgets(oc: OpiConverter) -> None:
    """Resize the screen to fit the widgets on it. This is useful for screens which have
    been converted from CS-Studio where the screen size was not set correctly."""

    max_width = 0
    max_height = 0

    # padding is applied to account for factors outside of the height/width properties
    # of a widget, such as border width and buttons expanding when highlighted.
    padding = 5  # px

    for widget in oc.bob_data.findall(".//widget"):
        x = get_widget_dimension(widget, "x")
        y = get_widget_dimension(widget, "y")
        width = get_widget_dimension(widget, "width")
        height = get_widget_dimension(widget, "height")

        if x + width > max_width:
            max_width = x + width
        if y + height > max_height:
            max_height = y + height

    root = oc.bob_data.getroot()
    screen_width = get_screen_width(root)
    screen_height = get_screen_height(root)

    new_width = max_width + padding
    new_height = max_height + padding

    # Only update the display dimensions if they are
    # too small to show all of the widgets
    if screen_width < max_width:
        if root.findtext("width") is None:
            etree.SubElement(root, "width").text = str(new_width)
        else:
            root.find("width").text = str(new_width)
        logging.info(f"Display width resized to: {new_width}")

    if screen_height < max_height:
        if root.findtext("height") is None:
            etree.SubElement(root, "height").text = str(new_height)
        else:
            root.find("height").text = str(new_height)
        logging.info(f"Display height resized to: {new_height}")


def fix_widget_issues(oc: OpiConverter, sc: ScreenConverter):
    for widget in oc.bob_data.findall(".//widget"):
        if "typeId" in widget.attrib.keys():
            logging.error(
                "Detected old CSS index '@typeid' - suggests that the Phoebus converter"
                "failed to convert the GroupContainer widget.\n"
                "Try running converter with --fixGroup option."
            )
            return

        widget_type = widget.attrib.get("type")
        if widget_type == "action_button":
            actions = widget.find("actions")
            if actions is not None:
                text = widget.find("text")
                if text is not None:
                    if (
                        text.text == "EXIT"
                        or text.text == "Exit"
                        or text.text == "Cancel"
                    ):
                        # We are assuming that there is only one action on this widget
                        # and so only update the first one we find.
                        fix_exit_button(oc, actions.find("action"))
                    fix_widget_actions(oc, actions)

        elif widget_type == "symbol":
            for child in widget:
                if child.tag == "actions":
                    fix_widget_actions(oc, widget.find(".//actions"))
            if sc is not None:
                fix_edm_symbol_widgets(oc, sc, widget)

        elif widget_type == "progressbar":
            # Actions are not supported on progressBars in Phoebus, so
            # we instead layer a transparent action button on top.
            for child in widget:
                if child.tag == "actions":
                    move_action_to_transparent_button(widget)
            # Look for any progress bar widgets with alarm borders enabled
            alarm_sensitive_progress_bars = get_alarm_sensitive_progress_bars(oc)
            if widget.find("name") is not None and widget.find("pv_name") is not None:
                if [
                    widget.find("name").text,
                    widget.find("pv_name").text,
                ] in alarm_sensitive_progress_bars:
                    widget.append(Element("border_alarm_sensitive"))
                    widget.find("border_alarm_sensitive").text = "true"

        elif widget_type == "tank":
            # Phoebus is missing the <transparent_background> option, so we just set the
            # background colour to transparent
            transparent_tank_backgrounds = get_transparent_background_tank_widget(oc)
            if widget.find("name") is not None and widget.find("pv_name") is not None:
                if [
                    widget.find("name").text,
                    widget.find("pv_name").text,
                ] in transparent_tank_backgrounds:
                    new_el = etree.fromstring(
                        "<background_color>\n<color name='Transparent' red='255' green='255' blue='255'></color>\n</background_color>\n"  # noqa: E501
                    )
                    widget.append(new_el)
        convert_pv_function(widget)
        fix_rule_expressions(oc, widget)
        fix_actions_on_widgets_without_actions_functionality(oc, widget)


def fix_exit_button(oc: OpiConverter, action: Element):
    oc.completed_conversion_steps.fix_exit_but = True
    action.attrib["type"] = "close_display"
    action.attrib["description"] = "Close display"
    description = action.find("description")
    if description is not None:
        description.text = "Close display"

    old_script = action.find("script")
    if old_script is not None:
        action.remove(old_script)


def fix_open_databrowser_actions(oc: OpiConverter, action: Element):
    """Fix custom scripts/commands used to launch the databrowser which dont work
    in Phoebus"""

    if action.attrib["type"] == "execute":
        script_text_el = action.find("script/text")
        if "executeEclipseCommand" in script_text_el.text:
            if "org.csstudio.trends.databrowser2" in script_text_el.text:
                search_string = script_text_el.text
                match = re.search(r"'pvnames',\s*'([^']+)'", search_string)
                if match:
                    pv_names = match.group(1)
                    pv_names = pv_names.split(",")
                    switch_to_new_databrowser_action(action, list(pv_names))
                else:
                    logger.error(
                        "Could not find any PV names to add to the open_data_browser"
                        f"action when converting the script: {search_string}"
                    )

            else:
                logger.warning(
                    "Screen contains an executeEclipseCommand script which is"
                    "not supported by Phoebus. Found script: "
                    f"{action.find('script/text').text} in file {oc.src_file_path}"
                )

    elif action.attrib["type"] == "command":
        if (
            "strip.py" in action.find("command").text
            or "strip.sh" in action.find("command").text
        ):
            search_string = action.find("command").text
            str_list = search_string.split(" ")
            pv_names = []
            for i, string in enumerate(str_list):
                if "strip.py" in string or "strip.sh" in string:
                    pv_names.extend(str_list[i + 1 : -1])
                    break
            switch_to_new_databrowser_action(action, list(pv_names))


def switch_to_new_databrowser_action(action: Element, pv_names: list[str]):
    """Remove the old action and replace with the new open_data_browser action."""

    new_action = Element("action", type="open_data_browser")
    etree.SubElement(new_action, "description").text = "Open Data Browser"
    etree.SubElement(new_action, "pv_name").text = " ".join(pv_names)
    etree.SubElement(new_action, "timeframe").text = "1 hour"

    # Add the new action
    action.getparent().append(new_action)
    # Delete the old action
    action.getparent().remove(action)


def fix_widget_actions(oc: OpiConverter, actions: Element):
    """Fix issues with widget actions"""

    for action in actions:
        fix_action_open_macro(oc, action)
        if oc.replace_tab:
            replace_open_in_tab(oc, action)

        fix_open_databrowser_actions(oc, action)


def fix_action_open_macro(oc: OpiConverter, action: Element):
    """Replace the macro $(name) with the actions parent widgets name"""

    if action.attrib["type"] == "open_display":
        for child in action:
            if child.tag == "macros":
                for macro in child:
                    if macro.text == "$(name)":
                        oc.completed_conversion_steps.fix_action_macro_name = True
                        macro.text = action.getparent().getparent().find("name").text


def get_symbol_image_dims(src_file: Path) -> tuple[int, int]:
    """Returns the width and height of an image file."""

    cmd = [
        "identify",
        "-format",
        "'%w %h'",
        str(src_file),
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        logger.error(f"identify - {stderr}")
        return None, None

    if stderr != "":
        logger.debug(f"identify - {stderr}")

    dims = stdout.decode().strip("'").split(" ")
    width = int(dims[0])
    height = int(dims[1])
    return width, height


def create_symbol_image_file(
    oc: OpiConverter,
    output_file: Path,
    output_file_full: Path,
    src_file: Path,
    n_images: int,
    width: int,
    height: int,
) -> list[str]:
    """Use the cli 'convert' tool to split the edm style single symbol image file
    into a seperate symbol image file per symbol"""

    symbol_files = []
    oc.completed_conversion_steps.create_sym_images = True
    logger.info(f"Creating new image for symbol from: {str(src_file)}")

    # Make directory for symbols if it doesnt exist. This can happen if we convert a
    # symbol widget which uses symbol files from a support module which has not been
    # scheduled for conversion. Normally we only mkdir for the support module when we
    # schedule it for conversion, so it is possible that this will happen too late or
    # wont happen if the user has not requested to convert dependencies.
    output_file_full.parent.mkdir(exist_ok=True)

    for n in range(n_images):
        x = 0 + width * n

        # If there is only 1 image file, we dont need to add an index
        if n_images == 1:
            new_symbol = str(output_file)
            new_output_file = output_file_full
        else:
            new_symbol = str(output_file.with_stem(output_file.stem + "_" + str(n)))
            new_output_file = output_file_full.with_stem(
                output_file_full.stem + "_" + str(n)
            )

        cmd = [
            "convert",
            str(src_file),
            "-crop",
            f"{str(width)}x{str(height)}+{str(x)}+0",
            str(new_output_file),
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = process.communicate()

        if not new_output_file.is_file():
            logger.error(
                f"Failed to create new symbol images with command: {' '.join(cmd)}"
            )
        for line in stderr.decode("utf-8").split("\n"):
            if line != "":
                if not new_output_file.is_file():
                    logger.error(f"convert - {line}")
                else:
                    logger.debug(f"convert - {line}")

        symbol_files.append(new_symbol)

    return symbol_files


def get_symbol_file_destinations(
    sc: ScreenConverter, oc: OpiConverter, src_file: Path, src_sm: str
) -> tuple[Path, Path]:
    """Get the destination path for the symbols, both the full path to save the image
    files too and the relative path to use in the screen links."""

    # Decide where to put the symbol files based on the name of either the support
    # module we got the image from (priority) or our own support module.
    sm = src_sm if src_sm is not None else oc.support_module_name

    if sm in ACC_UI_SUPPORT_MODULE_LIST:
        output_file = sc.acc_ui_support_symbol_dst_part / sm / src_file.name
        output_file_full = sc.acc_ui_support_symbol_dst_full / sm / src_file.name
    else:
        output_file = sc.domain_ui_support_symbol_dst_part / sm / src_file.name
        output_file_full = sc.domain_ui_support_symbol_dst_full / sm / src_file.name

    return oc.path_to_top / output_file, output_file_full


def update_symbol_widget_rules(
    widget: Element, output_file: Path
) -> tuple[int, Element | None]:
    """Modify/create rules to change the displayed symbol and overwrite the default
    order"""

    invalid_image_index = None
    old_rule = None
    if widget.findall("rules/rule") is not None:
        rules = widget.findall("rules/rule")
        additional_rules = []
        for rule in rules:
            # Look for a rule which is used to change the displayed
            # symbol to a symbol signifying an invalid state.
            if (
                "prop_id" in rule.attrib.keys()
                and rule.attrib["prop_id"] == "image_index"
            ):
                old_rule = copy.deepcopy(rule)
                rule.attrib["prop_id"] = "symbols[0]"
                rule.attrib["out_exp"] = "false"
                for exp in rule.findall("exp"):
                    if exp.attrib["bool_exp"] == "pvLegacySev0==-1":
                        invalid_image_index = int(exp.findtext("expression"))
                        exp.remove(exp.find("expression"))
                        exp.attrib["bool_exp"] = "pvSev0==3 || pvSev0==4"
                        val_el = Element("value")
                        val_el.text = str(
                            output_file.with_stem(
                                output_file.stem + "_" + str(invalid_image_index)
                            )
                        )
                        exp.append(val_el)
                    else:
                        # Remove other "image_index" rule expressions. Usually
                        # we dont want to keep these rules as for the most part
                        # this functionality is now built into the widget.
                        rule.remove(exp)

                # We must create a rule for each symbol specified for
                # the widget which overwrites the displayed symbol
                # widget with the special invalid state symbol.
                for i in range(1, len(widget.find("symbols"))):
                    # Get a unique copy of the rule
                    additional_rule = copy.deepcopy(rule)
                    additional_rule.attrib["name"] = rule.attrib["name"] + f"_{i}"
                    additional_rule.attrib["prop_id"] = f"symbols[{i}]"
                    additional_rules.append(additional_rule)

                # Extend the rules for this widget with the new rules we created
                rule.getparent().extend(additional_rules)

    if invalid_image_index is None:
        return 0, old_rule
    else:
        return 1, old_rule


def fix_edm_symbol_widgets(
    oc: OpiConverter, sc: ScreenConverter, widget: Element
) -> None:
    """Converts from an edm/cs-studio style symbol widget to a Pheobus style symbol
    widget."""

    # Get full list of support modules
    all_support_modules = (
        sc.domain_support_module_locations + sc.acc_support_module_locations
    )
    src_sm = None
    src_file = None

    # Get name of symbol file
    old_symbol_file = Path(widget.findtext("symbols/symbol"))
    if old_symbol_file.suffix == ".gif":
        logging.warning(
            "gif symbol images are not currently supported, failed to fix edm symbol: "
            f"{old_symbol_file}"
        )
        return

    resolved = fill_in_macros(str(old_symbol_file), oc.macros)
    if resolved is not None:
        old_symbol_file_resolved = Path(resolved)
        # Look for image file in external support modules
        for sm in all_support_modules:
            for i, part in enumerate(old_symbol_file_resolved.parts):
                if sm[0] == part:
                    sm_path = get_existing_support_module_filepath(part)
                    if sm_path is not None:
                        src_sm = part
                        # we have an absolute path to the support module:
                        # sm_path=/dls_sw/FE/3-10/ and a relative path
                        # within the support module:
                        # old_symbol_file_resolved=../FE/symbols/symbol.png
                        # which we want to merge to get the full symbol file path
                        src_file = Path(sm_path) / Path(
                            *old_symbol_file_resolved.parts[i + 1 :]
                        )
                        break

        # Look for symbol file within our own support module
        if src_file is None or not src_file.is_file():
            if oc.support_module_name is not None:
                # The old path is relative, but we want absolute so strip out ../
                old_symbol_file_stripped = str(old_symbol_file_resolved).replace(
                    "../", ""
                )
                src_file = Path(
                    get_existing_support_module_filepath(oc.support_module_name)
                ) / Path(old_symbol_file_stripped)

    if src_file is None or not src_file.is_file():
        logging.error(
            f"Could not find symbol image for symbol reference {old_symbol_file}"
        )
        return

    widget_name = widget.findtext("name")
    logger.info(f"Fixing Symbol widget with name: {widget_name}")

    output_file, output_file_full = get_symbol_file_destinations(
        sc, oc, src_file, src_sm
    )

    width = 0
    height = 0

    old_symbols_children = oc.const_opi_data.findall(".//sub_image_width")
    for symbol_child in old_symbols_children:
        symbol = symbol_child.getparent()
        if symbol.findtext("name") == widget_name and symbol.findtext(
            "image_file"
        ) == str(old_symbol_file):
            # sub_image_width stores a stringified float, so we must convert to float
            # first
            width = int(float(symbol.findtext("sub_image_width")))

    full_width, height = get_symbol_image_dims(src_file)
    if full_width is None or height is None:
        logging.error(
            "Failed to convert symbol widget due to problem with identify cmd"
        )
        return

    if width == 0:
        logging.warning(
            "Could not find symbol widget sub_image_width. Assuming width==height"
        )
        width = height
    # Need to calculate from width of full image / width
    n_images = full_width // width
    # Fix rules and return the start_index
    start_index, old_rule = update_symbol_widget_rules(widget, output_file)

    # Run action off left click if the widget has actions
    if widget.find("actions/action") is not None:
        widget.append(Element("run_actions_on_mouse_click"))
        widget.find("run_actions_on_mouse_click").text = "true"

    symbol_files = create_symbol_image_file(
        oc, output_file, output_file_full, src_file, n_images, width, height
    )

    # Remove the symbol files before the start index
    symbol_files = symbol_files[start_index:]

    # Reorder the symbol files based on rules
    if old_rule is not None:
        symbol_files = reorder_default_symbol_order_from_rule(symbol_files, old_rule)

    # Remove old combined symbol file
    symbols_el = widget.find("symbols")
    symbols_el.remove(symbols_el.find("symbol"))

    # Add new symbols
    for symbol_file in symbol_files:
        new_symbol = Element("symbol")
        new_symbol.text = symbol_file
        symbols_el.append(new_symbol)


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
        if widget.find("x") is not None:
            etree.SubElement(action_button, "x").text = widget.findtext("x")
        else:
            etree.SubElement(action_button, "x").text = "0"
        if widget.find("y") is not None:
            etree.SubElement(action_button, "y").text = widget.findtext("y")
        else:
            etree.SubElement(action_button, "y").text = "0"

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


def get_alarm_sensitive_progress_bars(oc: OpiConverter):
    """Get a list of identifying string pairs which are used to identify an
    alarm sensitive progressbar."""

    alarm_sensitive_progress_bars = []
    xpath = ".//widget[@typeId='org.csstudio.opibuilder.widgets.progressbar']"
    for widget in oc.const_opi_data.findall(xpath):
        if (
            (
                widget.find("backcolor_alarm_sensitive") is not None
                and widget.find("backcolor_alarm_sensitive").text == "true"
            )
            or (
                widget.find("forecolor_alarm_sensitive") is not None
                and widget.find("forecolor_alarm_sensitive").text == "true"
            )
            or (
                widget.find("fillcolor_alarm_sensitive") is not None
                and widget.find("fillcolor_alarm_sensitive").text == "true"
            )
        ):
            name_ids = [widget.find("name").text, widget.find("pv_name").text]
            alarm_sensitive_progress_bars.append(name_ids)

    return alarm_sensitive_progress_bars


def get_transparent_background_tank_widget(oc: OpiConverter):
    """Get a list of identifying string pairs which are used to identify a
    tank widget with a transparent background."""

    transparent_backgrounds = []
    xpath = ".//widget[@typeId='org.csstudio.opibuilder.widgets.tank']"
    for widget in oc.const_opi_data.findall(xpath):
        if widget.find("transparent_background").text == "true":
            name_ids = [widget.find("name").text, widget.find("pv_name").text]
            transparent_backgrounds.append(name_ids)

    return transparent_backgrounds


def fix_actions_on_widgets_without_actions_functionality(
    oc: OpiConverter, widget: Element
):
    """Some widgets which could have actions in CS-Studio, cannot have actions in
    Phoebus. We look for these situations and try to fix them by converting the widget
    to an action button which can have actions."""

    if widget.find(".actions/action") is not None:
        if (
            widget.attrib["type"] != "action_button"
            and widget.attrib["type"] != "symbol"
        ):
            oc.completed_conversion_steps.non_ab_action = True
            logger.debug(
                "Action contained in widget that isn't an action button: "
                + str(widget.attrib["type"])
                + ", name: "
                + str(widget.find("name").text)
            )
            logger.debug("    action: " + str(widget.find("actions/action").text))

            if (
                widget.attrib["type"] == "rectangle"
                or widget.attrib["type"] == "bool_button"
            ):
                if widget.attrib["type"] == "bool_button":
                    if widget.find("on_label").text != widget.find("off_label").text:
                        return

                oc.completed_conversion_steps.replace_with_ab = True
                logger.debug("    Attempting to fix by converting to an action_button")
                widget.attrib["type"] = "action_button"

                if (
                    widget.find("text") is not None
                    and widget.find("off_label") is not None
                ):
                    widget.find("text").text = widget.find("off_label").text
                else:
                    text_el = Element("text")
                    text_el.text = ""
                    widget.append(text_el)
                for rule in widget.findall("rules/rule"):
                    if rule.attrib["prop_id"] == "line_color":
                        rule.getparent().remove(rule)


def replace_open_in_tab(oc: OpiConverter, action: Element):
    if action.attrib["type"] == "open_display":
        for child in action:
            if child.tag == "target" and child.text == "tab":
                child.text = "standalone"
                oc.completed_conversion_steps.replace_action_tab = True


def reorder_default_symbol_order_from_rule(
    symbols: list[str], rule: Element
) -> list[str]:
    """Some rules in cs-studio were used to change the displayed symbol based on a
    PV value. In Phoebus we are able to do this more cleanly by directly associating
    a symbol file with a PV value by the order in which symbol files are defined.

    eg. symbols[0] is displayed for a pv value of 0, symbols[1] for a value of 1 etc.

    Here we search through all the boolean expressions in the cs-studio rule and create
    a map between the PV value and the symbol index to use (reorder_map).

    We only bother to handle 2 cases,
    - pvX == Y
    - pvX >= Y && pvX < Z

    This map is then used to reorder the list of symbol files which is returned and the
    old rule is removed"""

    # Contains a list of tuples of (pv_val, symbol_index)
    reorder_map: list[tuple] = []
    for exp in rule.findall("exp"):
        pv_val = None
        result = int(exp.find("expression").text)
        bool_logic = exp.attrib["bool_exp"]
        bool_logic = bool_logic.replace(" ", "")
        # Match for pvX in string
        if re.findall(r"pv\d+", bool_logic):
            if "==" in bool_logic:
                match = re.search(r"==\s*(\d+)", bool_logic)
                if match:
                    pv_val = int(match.group(1))
            elif ">=" in bool_logic and "<" in bool_logic and "&&" in bool_logic:
                # Gets the integer between >= and &&. This could be made
                # smarter if required
                match = re.search(r">=\s*(.+?)\s*&&", bool_logic)
                if match:
                    pv_val = int(float(match.group(1)))
            reorder_map.append((pv_val, result))

    if len(reorder_map) == 0:
        logger.warning(
            "Failed to parse symbol widget index modification rule when "
            "attempting to reorder symbol widget. Rule is being ignored."
        )
        return symbols
    else:
        # Sort the map by ascending pv_val
        reorder_map = sorted(reorder_map, key=lambda x: x[0])
        new_symbols_order = list(symbols)
        for pv_val, index in reorder_map:
            for symbol in symbols:
                if pv_val >= len(new_symbols_order):
                    # Sometimes rules can specify a symbol to use for a pv_value outside
                    # the number of images, we handle this by adding it to the end
                    new_symbols_order.append(symbol)
                elif f"_{index}." in symbol:
                    new_symbols_order[pv_val] = symbol

        return new_symbols_order


def convert_pv_function(widget: Element):
    for child in widget.iter():
        inp_string = child.text
        if inp_string is not None and "pv(" in inp_string:
            pv_replacement = "".join(
                [
                    g
                    if i == 0
                    else g
                    if (k := g.find('")')) < 0
                    else "`" + g[:k] + "`" + g[k + 2 :]
                    for (i, g) in enumerate(inp_string.split('pv("'))
                ]
            )
            # Catch case where there is a function call nested within a pv(...) function
            # In this case the above replacement will not have found pv(" and so it
            # will still exist in the replacement. There is no way to handle this in
            # Phoebus so just issue warning
            if "pv(" in pv_replacement:
                logger.warning(
                    "Cannot fix the following formula in Phoebus " + inp_string
                )
            else:
                logger.info("Replace pv() function with " + pv_replacement)
                child.text = pv_replacement


def fix_rule_expressions(oc, widget: Element):
    """Fix common issues that come up in cs-studio rules"""

    expressions = widget.findall("rules/rule/exp")
    for exp in expressions:
        # Use new syntax for getting a PV alarm severity
        fix_pv_severity_expression(oc, exp)

        # widget.getValue() is not available in Phoebus, we assume this is an attempt to
        # get the value of the widgets pv, so we replace it with pv0
        if "widget.getValue()" in exp.attrib["bool_exp"]:
            exp.attrib["bool_exp"] = exp.attrib["bool_exp"].replace(
                "widget.getValue()", "pv0"
            )


def fix_pv_severity_expression(oc: OpiConverter, exp_el: Element):
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
            oc.completed_conversion_steps.update_leg_sev = True
            modified_attrib = initial_attrib.replace(css_exp, phoebus_exp)
            logger.debug(f"Fixing {css_exp} to {phoebus_exp} in rule")

    exp_el.attrib["bool_exp"] = modified_attrib


def update_legacy_sev_status(oc: OpiConverter, input_field, leg_sev, new_sev):
    if leg_sev in input_field:
        oc.completed_conversion_steps.update_leg_sev = True
        result = input_field.replace(leg_sev, new_sev)
        logger.debug(f"Fixing {leg_sev} to {new_sev}")
        return result
    else:
        return input_field
