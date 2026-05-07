"""Extra conversion steps which arent handled by the phoebus converter"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import TYPE_CHECKING

import xmltodict

from dls_phoebus_converter.logconfig import setup_logging
from dls_phoebus_converter.macros import handle_macros

if TYPE_CHECKING:
    from dls_phoebus_converter.opi_converter import OpiConverter
from dls_phoebus_converter.support_modules import handle_support_modules

if not logging.getLogger("dls_phoebus_converter"):
    setup_logging()
logger = logging.getLogger("dls_phoebus_converter")


def post_conversion_steps(oc: OpiConverter):
    if not oc.no_modify:
        xml_dict = modify_bob_xml(oc)
        # Write out modified xml
        if xml_dict is not None:
            write_dict(xml_dict)
        else:
            # Dictionary could not be parsed
            return None

    # We need to define macros which were previously passed into the synoptic as
    # script arguments
    if oc.synoptic:
        handle_macros(oc)

    handle_support_modules(oc)

    # Special cases are tweaks which are not handled by the
    # normal conversion process and are often unique to a specific screen.
    # These are optionally defined in a domain-specific special case module.
    try:
        oc.special_case_module.run(oc)
    except AttributeError:
        pass


def modify_bob_xml(oc: OpiConverter):
    as_dict = {}
    with open(os.path.join(oc.dst_dir_path, oc.dst_filename), encoding="utf-8") as file:
        fxml = file.read()

        as_dict = xmltodict.parse(fxml)
        try:
            widgets = as_dict["display"]["widget"]
        except KeyError as e:
            logger.error(
                f"Failed to parse xml for file: {oc.src_file_path} with error:\n{e}"
            )
            return None

        for w in widgets:
            parse_widget(w, "", 0, as_dict["display"])

    return as_dict


# TODO: This will move to utilities and be made common. It will also switch to lxml
def parse_widget(oc: OpiConverter, widget, spacing, level, parent):

    if not isinstance(widget, dict):
        return

    if "@typeId" in widget:
        logging.error(
            "Detected old CSS index '@typeid' - suggests that the Phoebus converter"
            "failed to convert the GroupContainer widget.\n"
            "Try running converter with --fixGroup option."
        )
        return

    if widget["@type"] == "group":
        if "widget" in widget:
            if type(widget["widget"]) is not list:
                parse_widget(widget["widget"], spacing + " ", level + 1, widget)
            else:
                for w in widget["widget"]:
                    parse_widget(w, spacing + " ", level + 1, widget)
    elif widget["@type"] == "tabs":
        if "tabs" in widget:
            if "tab" in widget["tabs"]:
                if type(widget["tabs"]["tab"]) is not list:
                    if type(widget["tabs"]["tab"]["children"]["widget"]) is not list:
                        parse_widget(
                            widget["tabs"]["tab"]["children"]["widget"],
                            spacing + " ",
                            level + 1,
                            widget,
                        )
                    else:
                        for child_widget in widget["tabs"]["tab"]["children"]["widget"]:
                            parse_widget(child_widget, spacing + " ", level + 1, widget)
                else:
                    for tab in widget["tabs"]["tab"]:
                        if type(tab["children"]["widget"]) is not list:
                            parse_widget(
                                tab["children"]["widget"],
                                spacing + " ",
                                level + 1,
                                widget,
                            )
                        else:
                            for child_widget in tab["children"]["widget"]:
                                parse_widget(
                                    child_widget, spacing + " ", level + 1, widget
                                )
    elif widget["@type"] == "action_button":
        if "text" in widget:
            if (
                widget["text"] == "EXIT"
                or widget["text"] == "Exit"
                or widget["text"] == "Cancel"
            ):
                widget["actions"]["action"] = fix_exit_button(oc)
        if widget["actions"] is not None:
            process_widget_actions(oc, widget)

    elif widget["@type"] == "symbol":
        if "actions" in widget:
            if widget["actions"] is not None and "action" in widget["actions"]:
                replace_opi_extension(widget["actions"]["action"])
                fix_action_open_macro(widget)
        create_symbol_from_edm(widget)
    elif widget["@type"] == "embedded":
        fix_embedded_screen_ext(widget)
    elif widget["@type"] == "progressbar":
        # Look for any progress bar widgets with alarm borders enabled
        alarm_sensitive_progress_bars = get_alarm_sensitive_progress_bars()
        if "name" in widget and "pv_name" in widget:
            if [widget["name"], widget["pv_name"]] in alarm_sensitive_progress_bars:
                widget["border_alarm_sensitive"] = "true"
    elif widget["@type"] == "tank":
        # Phoebus is missing the <transparent_background> option, so we just set the
        # background colour to transparent
        transparent_tank_backgrounds = get_transparent_background_tank_widget()
        if "name" in widget and "pv_name" in widget:
            if [widget["name"], widget["pv_name"]] in transparent_tank_backgrounds:
                widget["background_color"] = {
                    "color": {
                        "@name": "Transparent",
                        "@red": "255",
                        "@green": "255",
                        "@blue": "255",
                    }
                }

    parse_all_fields_in_dict(widget)
    check_rule(widget)
    check_actions_in_non_action_buttons(widget)


def fix_exit_button(oc):
    oc.fix_exit_but = True
    new_action = {}
    new_action["@type"] = "close_display"
    new_action["description"] = "Close display"
    return new_action


def process_widget_actions(oc, widget):
    actions = widget["actions"]["action"]
    if type(actions) is not list:
        actions = [actions]

    for action in actions:
        replace_opi_extension(action)
        if oc.replace_tab:
            replace_open_in_tab(action)

        # Currently we are only looking at databrowser/StripTool related actions
        if action["@type"] == "execute":
            if "executeEclipseCommand" in action["script"]["text"]:
                if "org.csstudio.trends.databrowser2" in action["script"]["text"]:
                    set_new_databrowser_action_from_execute_eclipse(action)
                else:
                    logger.warning(
                        "Screen contains an executeEclipseCommand script which is"
                        "not supported by Phoebus. Found script: "
                        f"{action['script']['text']} in file {oc.src_file_path}"
                    )

        elif action["@type"] == "command":
            if "strip.py" in action["command"]:
                set_new_databrowser_action_from_strip_command(action)


def replace_opi_extension(oc: OpiConverter, action):
    if "file" in action:
        oc.conversion_steps.replace_opi_ext = True
        logger.debug(
            "Replacing file open action: " + str(action["file"]) + " to open .BOB file"
        )
        opi = action["file"]
        bob = opi.replace(".opi", ".bob")
        action["file"] = bob


def fix_action_open_macro(oc: OpiConverter, widget):
    actions = widget["actions"]["action"]
    if type(actions) is not list:
        actions = [actions]
    for action in actions:
        if action["@type"] == "open_display":
            if "macros" in action.keys():
                for i in action["macros"]:
                    if action["macros"][i] == "$(name)":
                        oc.conversion_steps.fix_action_macro_name = True
                        action["macros"][i] = widget["name"]


def create_symbol_from_edm(oc: OpiConverter, widget):
    setup_dict = {}
    if oc.template_file_path is None:
        logger.warning(
            "Found edm symbol widget but could not convert it due to no template"
            "file being supplied."
        )
        return

    if not os.path.isfile(oc.template_file_path):
        error_msg = "No template file provided"
        logger.error(error_msg, exc_info=True)
        raise FileNotFoundError(error_msg)

    with open(oc.template_file_path, encoding="utf-8") as file:
        fxml = file.read()

        setup_dict = xmltodict.parse(fxml)

        sym_list = []
        if type(setup_dict["symbols"]["symbol"]) is not list:
            sym_list = [setup_dict["symbols"]["symbol"]]
        else:
            sym_list = setup_dict["symbols"]["symbol"]
        for s in sym_list:
            if s["name"] == widget["name"]:
                logger.info("Fixing Symbol widget with name: " + s["name"])
                image = s["image"]
                location = s["location"]
                width = int(s["width"])
                height = int(s["height"])
                n_images = int(s["nimages"])
                start_index = s["startindex"]
                invalid_image_index = int(s["invalidimageindex"])

                # Run action of left click
                if "actions" in widget:
                    widget["run_actions_on_mouse_click"] = "true"

                # Set up symbols
                out_image = location.split(".")[:-1]
                ext = "." + location.split(".")[-1]
                logger.info("Creating new images for symbol from: " + location)
                if os.path.isfile(out_image[0] + "_0" + ext):
                    logger.info("   ... images already exist - skipping")
                else:
                    oc.conversion_steps.create_sym_images = True
                    for n in range(n_images):
                        output = out_image[0] + "_" + str(n) + ext
                        x = 0 + width * n
                        cmd = (
                            "convert "
                            + location
                            + " -crop "
                            + str(width)
                            + "x"
                            + str(height)
                            + "+"
                            + str(x)
                            + "+0 "
                            + output
                        )
                        process = subprocess.Popen(
                            cmd.split(),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )

                        stdout, stderr = process.communicate()

                out_image = ".".join(image.split(".")[:-1])
                ext = "." + image.split(".")[-1]
                symbols = []
                start_index_list = start_index.split(",")
                if len(start_index_list) > 1:
                    for n in start_index_list:
                        symbols.append(out_image + "_" + n + ext)
                else:
                    for n in range(n_images - int(start_index_list[0])):
                        index = n + int(start_index_list[0])
                        symbols.append(out_image + "_" + str(index) + ext)

                widget["symbols"]["symbol"] = symbols

                if "rules" in widget:
                    additional_rules = []
                    rules = widget["rules"]["rule"]

                    if type(rules) is not list:
                        rules = [rules]

                    for rule in rules:
                        # We look through the rules and see if we need to re-order
                        # any symbols
                        if rule["@prop_id"] == "image_index":
                            widget["symbols"]["symbol"] = reorder_widgets_from_rules(
                                symbols, rule
                            )

                        # Look for a rule which is used to change the displayed
                        # symbol to a symbol signifying an invalid state.
                        if rule["@prop_id"] == "image_index":
                            rule["@prop_id"] = "symbols[0]"
                            rule["@out_exp"] = "false"
                            expression = {}
                            for e in rule["exp"]:
                                if e["@bool_exp"] == "pvLegacySev0==-1":
                                    expression["@bool_exp"] = "pvSev0==3 || pvSev0==4"
                                    expression["value"] = (
                                        out_image + "_" + str(invalid_image_index) + ext
                                    )
                            rule["exp"] = expression

                            # We must create a rule for each symbol specified for
                            # the widget which overwrites the displayed symbol
                            # widget with the special invalid state symbol.
                            for i in range(1, len(widget["symbols"]["symbol"])):
                                # Copy dictionary to get a unique copy
                                additional_rule = rule.copy()
                                additional_rule["@name"] = rule["@name"] + f"_{i}"
                                additional_rule["@prop_id"] = f"symbols[{i}]"
                                additional_rules.append(additional_rule)

                    # Extend the rules for this widget with the new rules we created
                    rules.extend(additional_rules)
                    widget["rules"]["rule"] = rules


def fix_embedded_screen_ext(oc: OpiConverter, widget):
    if "file" not in widget:
        return
    oc.conversion_steps.replace_opi_ext = True
    opi_file = widget["file"]
    bob_file = opi_file.replace(".opi", ".bob")
    widget["file"] = bob_file


def get_alarm_sensitive_progress_bars(oc: OpiConverter):
    alarm_sensitive_progress_bars = []
    in_progress_bar = False
    alarm_sensitive = False
    name_ids = ["", ""]
    with open(oc.src_file_path) as f:
        lines = f.readlines()
        for line in lines:
            if "org.csstudio.opibuilder.widgets.progressbar" in line:
                in_progress_bar = True
            if "</widget>" in line:
                if alarm_sensitive:
                    alarm_sensitive_progress_bars.append(name_ids)
                in_progress_bar = False
                name_ids = ["", ""]
                alarm_sensitive = False
            if in_progress_bar:
                if "<name>" in line:
                    name_ids[0] = re.search(r"<name>(.*?)</name>", line).group(1)
                if "<pv_name>" in line:
                    name_ids[1] = re.search(r"<pv_name>(.*?)</pv_name>", line).group(1)
                if (
                    "<fillcolor_alarm_sensitive>true</fillcolor_alarm_sensitive>"
                    in line
                    or "<forecolor_alarm_sensitive>true</forecolor_alarm_sensitive>"
                    in line
                    or "<backcolor_alarm_sensitive>true</backcolor_alarm_sensitive>"
                    in line
                ):
                    alarm_sensitive = True
    return alarm_sensitive_progress_bars


def get_transparent_background_tank_widget(oc: OpiConverter):
    in_tank_widget = False
    transparent_background = False
    transparent_backgrounds = []
    name_ids = ["", ""]
    with open(oc.src_file_path) as f:
        lines = f.readlines()
        for line in lines:
            if "org.csstudio.opibuilder.widgets.tank" in line:
                in_tank_widget = True
            if "</widget>" in line:
                if transparent_background:
                    transparent_backgrounds.append(name_ids)
                in_tank_widget = False
                name_ids = ["", ""]
                transparent_background = False
            if in_tank_widget:
                if "<name>" in line:
                    name_ids[0] = re.search(r"<name>(.*?)</name>", line).group(1)
                if "<pv_name>" in line:
                    name_ids[1] = re.search(r"<pv_name>(.*?)</pv_name>", line).group(1)
                if "<transparent_background>true</transparent_background>" in line:
                    transparent_background = True
    return transparent_backgrounds


def parse_all_fields_in_dict(input_dict):
    for field in input_dict:
        if type(input_dict[field]) is dict:
            parse_all_fields_in_dict(input_dict[field])
        elif type(input_dict[field]) is list:
            for item in input_dict[field]:
                if type(item) is dict:
                    parse_all_fields_in_dict(item)
                else:
                    find_pv_function_in_field(input_dict, field)
        else:
            find_pv_function_in_field(input_dict, field)


def check_rule(widget):
    if "rules" in widget and "rule" in widget["rules"]:
        rules = widget["rules"]["rule"]
        if type(rules) is not list:
            rules = [rules]

        for rule in rules:
            if "exp" in rule:
                rule_exprs = rule["exp"]
                if type(rule_exprs) is not list:
                    rule_exprs = [rule_exprs]
                for e in rule_exprs:
                    fix_rule_expression(e)


def check_actions_in_non_action_buttons(oc: OpiConverter, widget):
    if "actions" in widget:
        if (
            widget["actions"] is not None
            and "action" in widget["actions"]
            and widget["@type"] != "action_button"
            and widget["@type"] != "symbol"
        ):
            oc.conversion_steps.non_ab_action = True
            logger.debug(
                "Action contained in widget that isn't an action button: "
                + str(widget["@type"])
                + ", name: "
                + str(widget["name"])
            )
            logger.debug("    action: " + str(widget["actions"]["action"]))
            if widget["@type"] == "rectangle" or widget["@type"] == "bool_button":
                if widget["@type"] == "bool_button":
                    if widget["on_label"] != widget["off_label"]:
                        return
                oc.conversion_steps.replace_with_ab = True
                logger.debug("    Attempting to fix by converting to an action_button")
                widget["@type"] = "action_button"

                if "on_label" in widget:
                    widget["text"] = widget["on_label"]
                else:
                    widget["text"] = ""
                if "rules" in widget:
                    if type(widget["rules"]["rule"]) is list:
                        for r in widget["rules"]["rule"]:
                            if r["@prop_id"] == "line_color":
                                widget["rules"]["rule"].remove(r)
                    else:
                        if widget["rules"]["rule"]["@prop_id"] == "line_color":
                            widget["rules"]["rule"].remove(r)


def replace_open_in_tab(oc: OpiConverter, action):
    if action["@type"] == "open_display":
        if action["target"] == "tab":
            action["target"] = "standalone"
            oc.conversion_steps.replace_action_tab = True


def set_new_databrowser_action_from_execute_eclipse(action):
    # We will be implementing a new Phoebus action which opens PV(s) in the
    # databrowser, so eventually this code will be replaced with that, for now we
    # use a command action.
    search_string = action["script"]["text"]
    match = re.search(r"'pvnames',\s*'([^']+)'", search_string)
    if match:
        pv_names = match.group(1)
        pv_names = pv_names.split(",")
    else:
        logger.error(f"Could not find PV name from script text: {search_string}")
        pass

    pv_command_str = "pv://?"
    for pv in pv_names:
        pv_command_str += f"{pv}&"

    action["@type"] = "command"
    action["description"] = "Launch databrowser"
    action["command"] = (
        f'$(phoebus.install)/../phoebus.sh -resource "{pv_command_str}app=databrowser'  # noqa: E501
    )


def set_new_databrowser_action_from_strip_command(action):
    # We will be implementing a new Phoebus action which opens PV(s) in the
    # databrowser, so eventually this code will be replaced with that, for now we
    # use a command action.
    search_string = action["command"]
    str_list = search_string.split(" ")
    for i, string in enumerate(str_list):
        if "strip.py" in string:
            pv_names = str_list[i + 1 : -1]
            break

    if type(pv_names) is not list:
        pv_names = [pv_names]
    pv_command_str = "pv://?"
    for pv in pv_names:
        pv_command_str += f"{pv}&"

    action["@type"] = "command"
    action["description"] = "Launch databrowser"
    action["command"] = (
        f'$(phoebus.install)/../phoebus.sh -resource "{pv_command_str}app=databrowser'  # noqa: E501
    )


def reorder_widgets_from_rules(symbols, rule):
    # Search through all boolean expressions and create a map between the PV value
    # and the symbol index to use.
    # We only bother to handle 2 cases,
    # - pvX == Y
    # - pvX >= Y && pvX < Z

    # Contains a list of tuples of (pv_val, symbol_index)
    reorder_map: list[tuple] = []
    try:
        if "exp" in rule:
            for e in rule["exp"]:
                pv_val = None
                result = int(e["expression"])
                bool_logic = e["@bool_exp"]
                bool_logic = bool_logic.replace(" ", "")
                # Match for pvX in string
                if re.findall(r"pv\d+", bool_logic):
                    if "==" in bool_logic:
                        match = re.search(r"==\s*(\d+)", bool_logic)
                        if match:
                            pv_val = int(match.group(1))
                    elif (
                        ">=" in bool_logic and "<" in bool_logic and "&&" in bool_logic
                    ):
                        # Gets the integer between >= and &&. This could be made
                        # smarter if required
                        match = re.search(r">=\s*(.+?)\s*&&", bool_logic)
                        if match:
                            pv_val = int(float(match.group(1)))
                    reorder_map.append((pv_val, result))

    except (LookupError, ValueError):
        logger.warning("Failed to parse rule when attempting to reorder symbol widget.")

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


def find_pv_function_in_field(widget, field):
    # Some fields may contain lists
    if type(widget[field]) is list:
        for i in range(len(widget[field])):
            widget[field][i] = convert_pv_function(widget[field][i])
    else:
        widget[field] = convert_pv_function(widget[field])


def convert_pv_function(inp_string):
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
            logger.warning("Cannot fix the following formula in Phoebus " + inp_string)
        else:
            logger.info("Replace pv() function with " + pv_replacement)
            return pv_replacement

    # Otherwise return the original
    return inp_string


def fix_rule_expression(expression):
    """Fix common issues that come up in cs-studio rules"""

    # Use new syntax for getting a PV alarm severity
    expression["@bool_exp"] = check_legacy_sev(expression["@bool_exp"])

    # widget.getValue() is not available in Phoebus, we assume this is an attempt to
    # get the value of the widgets pv, so we replace it with pv0
    if "widget.getValue()" in expression["@bool_exp"]:
        expression["@bool_exp"] = expression["@bool_exp"].replace(
            "widget.getValue()", "pv0"
        )


def check_legacy_sev(input_field):
    # OK, Major, Minor, Invalid/undefined
    legacy = [
        "pvLegacySev0==0",
        "pvLegacySev0==1",
        "pvLegacySev0==2",
        "pvLegacySev0==-1",
    ]
    new_v = ["pvSev0==0", "pvSev0==2", "pvSev0==1", "pvSev0==3"]
    result = input_field
    for i in range(len(legacy)):
        result = update_legacy_sev_status(result, legacy[i], new_v[i])
    return result


def update_legacy_sev_status(oc: OpiConverter, input_field, leg_sev, new_sev):
    if leg_sev in input_field:
        oc.conversion_steps.update_leg_sev = True
        result = input_field.replace(leg_sev, new_sev)
        logger.debug("Fixing " + leg_sev + " to " + new_sev)
        return result
    else:
        return input_field


def write_dict(self, as_dict):
    with open(os.path.join(self.dst_dir_path, self.dst_filename), "w") as f:
        new_xml = xmltodict.unparse(as_dict, pretty=True)
        f.write(new_xml)
