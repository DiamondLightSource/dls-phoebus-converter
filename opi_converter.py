from pathlib import Path
import re
import shutil
import subprocess
import os
import xmltodict
import argparse
from dataclasses import dataclass
import logging
from logconfig import setup_logging

PHOEBUS_SH_FILE_PATH = "/dls_sw/deploy-tools/modules/phoebus/dev/entrypoints/phoebus"
PLOT_LOCATION_MACRO = "$(PLOT_LOC)"

if not logging.getLogger("dls_phoebus_converter"):
    setup_logging()
logger = logging.getLogger("dls_phoebus_converter")


@dataclass
class ConversionSteps:
    replace_edm_sym = False
    fix_group_cont = False
    update_leg_sev = False
    fix_exit_but = False
    replace_opi_ext = False
    non_ab_action = False
    replace_with_ab = False
    replace_db_script = False
    fix_open_action_name = False
    fix_action_macro_name = False
    create_sym_images = False
    replace_action_tab = False


class ScreenConverter:
    def __init__(
        self,
        src_file_path,
        dst_filename,
        dst_dir_path,
        tmp_file_path,
        template_file_path,
        replace_tab,
    ):
        self.src_file_path = src_file_path
        self.dst_filename = dst_filename
        self.dst_dir_path = dst_dir_path
        self.tmp_file_path = tmp_file_path
        self.template_file_path = template_file_path
        self.replace_tab = replace_tab
        self.cs = ConversionSteps()

    def get_transparent_background_tank_widget(self):
        in_tank_widget = False
        transparent_background = False
        transparent_backgrounds = []
        name_ids = ["", ""]
        with open(self.src_file_path, "r") as f:
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
                        name_ids[0] = re.search(r'<name>(.*?)</name>', line).group(1)
                    if "<pv_name>" in line:
                        name_ids[1] = re.search(r'<pv_name>(.*?)</pv_name>', line).group(1)
                    if "<transparent_background>true</transparent_background>" in line:
                        transparent_background = True
        return transparent_backgrounds

    def get_alarm_sensitive_progress_bars(self):
        alarm_sensitive_progress_bars = []
        in_progress_bar = False
        alarm_sensitive = False
        name_ids = ["", ""]
        with open(self.src_file_path, "r") as f:
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
                        name_ids[0] = re.search(r'<name>(.*?)</name>', line).group(1)
                    if "<pv_name>" in line:
                        name_ids[1] = re.search(r'<pv_name>(.*?)</pv_name>', line).group(1)
                    if "<fillcolor_alarm_sensitive>true</fillcolor_alarm_sensitive>" in line or \
                    "<forecolor_alarm_sensitive>true</forecolor_alarm_sensitive>" in line or \
                    "<backcolor_alarm_sensitive>true</backcolor_alarm_sensitive>" in line:
                        alarm_sensitive = True
        return alarm_sensitive_progress_bars

    def replace_edm_symbol_widget(self):
        result = []
        with open(self.src_file_path, "r") as f:
            lines = f.readlines()
            fixed = False
            for line in lines:
                if "org.csstudio.opibuilder.widgets.edm.symbolwidget" in line:
                    line = line.replace(
                        "org.csstudio.opibuilder.widgets.edm.symbolwidget",
                        "org.csstudio.opibuilder.widgets.symbol.multistate.MultistateMonitorWidget",
                    )
                    fixed = True
                result.append(line)
        if fixed:
            self.cs.replace_edm_sym = True
            logger.debug("Replacing CSS EDM Widgets in OPI before conversion")
            with open(self.tmp_file_path, "w") as f:
                f.writelines(result)

        return fixed

    def delete_old_file(self):
        try:
            old_file = os.path.join(self.dst_dir_path, self.dst_filename)
            os.remove(old_file)
            logger.info(f"Removing old converted file: {old_file}")
        except OSError:
            pass

    def run_converter(self, opi_file_path):
        convert_command = (
            PHOEBUS_SH_FILE_PATH
            + "\
        -main org.csstudio.display.builder.model.Converter -output "
            + str(self.dst_dir_path)
            + " "
            + str(opi_file_path)
        )
        process = subprocess.Popen(
            convert_command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        output_file = self.dst_dir_path / "tmp.bob"

        # Captures the stdout and stderr from the converter process.
        # This can be very verbose, so we log it at the DEBUG level
        stdout, stderr = process.communicate()
        if not output_file.is_file():
            logger.error(f"Phoebus conversion command failed: {convert_command}")
        for line in stderr.decode("utf-8").split("\n"):
            if not output_file.is_file():
                logger.error(line)
            logger.debug(line)

        if not output_file.is_file():
            return False
        else:
            return True

    def update_legacy_sev_status(self, input_field, leg_sev, new_sev):
        if leg_sev in input_field:
            self.cs.update_leg_sev = True
            result = input_field.replace(leg_sev, new_sev)
            logger.debug("Fixing " + leg_sev + " to " + new_sev)
            return result
        else:
            return input_field

    def check_legacy_sev(self, input_field):
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
            result = self.update_legacy_sev_status(result, legacy[i], new_v[i])
        return result

    def check_rule(self, widget):
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
                        self.fix_rule_expression(e)

    def fix_rule_expression(self, expression):
        """Fix common issues that come up in cs-studio rules"""

        # Use new syntax for getting a PV alarm severity
        expression["@bool_exp"] = self.check_legacy_sev(expression["@bool_exp"])

        # widget.getValue() is not available in Phoebus, we assume this is an attempt to get the
        # value of the widgets pv, so we replace it with pv0
        if "widget.getValue()" in expression["@bool_exp"]:
            expression["@bool_exp"] = expression["@bool_exp"].replace("widget.getValue()", "pv0")

    def fix_exit_button(self):
        self.cs.fix_exit_but = True
        new_action = {}
        new_action["@type"] = "close_display"
        new_action["description"] = "Close display"
        return new_action

    def replace_opi_extension(self, action):
        if "file" in action:
            self.cs.replace_opi_ext = True
            logger.debug(
                "Replacing file open action: "
                + str(action["file"])
                + " to open .BOB file"
            )
            opi = action["file"]
            bob = opi.replace(".opi", ".bob")
            action["file"] = bob

    def replace_open_in_tab(self, action):
        if action["@type"] == "open_display":
            if action["target"] == "tab":
                action["target"] = "standalone"
                self.cs.replace_action_tab = True

    def check_actions_in_non_action_buttons(self, widget):
        if "actions" in widget:
            if (
                widget["actions"] is not None
                and "action" in widget["actions"]
                and widget["@type"] != "action_button"
                and widget["@type"] != "symbol"
            ):
                self.cs.non_ab_action = True
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
                    self.cs.replace_with_ab = True
                    logger.debug(
                        "    Attempting to fix by converting to an action_button"
                    )
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


    def process_widget_actions(self, widget):
        actions = widget["actions"]["action"]
        if type(actions) is not list:
            actions = [actions]

        for action in actions:
            self.replace_opi_extension(action)
            if self.replace_tab:
                self.replace_open_in_tab(action)

            # Currently we are only looking at databrowser/StripTool related actions
            if action["@type"] == "execute":
                if "executeEclipseCommand" in action["script"]["text"]:
                    if "org.csstudio.trends.databrowser2" in action["script"]["text"]:
                        self.set_new_databrowser_action_from_execute_eclipse(action)
                    else:
                        logger.warning("Screen contains an executeEclipseCommand script which is not supported by Phoebus." \
                        f'Found script: {action["script"]["text"]} in file {self.src_file_path}')

            elif action["@type"] == "command":
                if "strip.py" in action["command"]:
                    self.set_new_databrowser_action_from_strip_command(action)

    def set_new_databrowser_action_from_strip_command(self, action):
        # We will be implementing a new Phoebus action which opens PV(s) in the databrowser, so
        # eventually this code will be replaced with that, for now we use a command action.
        search_string = action["command"]
        str_list = search_string.split(" ")
        for i, string in enumerate(str_list):
            if "strip.py" in string:
                pv_names = str_list[i+1:-1]
                break

        if type(pv_names) is not list:
            pv_names = [pv_names]
        pv_command_str = "pv://?"
        for pv in pv_names:
            pv_command_str += f"{pv}&"

        action["@type"] = "command"
        action["description"] = "Launch databrowser"
        action["command"] = f'$(phoebus.install)/../phoebus.sh -resource "{pv_command_str}app=databrowser'

    def set_new_databrowser_action_from_execute_eclipse(self, action):
        # We will be implementing a new Phoebus action which opens PV(s) in the databrowser, so
        # eventually this code will be replaced with that, for now we use a command action.
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
        action["command"] = f'$(phoebus.install)/../phoebus.sh -resource "{pv_command_str}app=databrowser'

    def fix_embedded_screen_ext(self, widget):
        if "file" not in widget:
            return
        self.cs.replace_opi_ext = True
        opi_file = widget["file"]
        bob_file = opi_file.replace(".opi", ".bob")
        widget["file"] = bob_file

    def fix_grouping_container(self, opi_file_path):
        result = []
        with open(opi_file_path, "r") as f:
            lines = f.readlines()
            check_for_border_prop = False
            found_border_prop = False
            fixed = False
            for line in lines:
                if (
                    "org.csstudio.opibuilder.widgets.groupingContainer" in line
                    and not check_for_border_prop
                ):
                    check_for_border_prop = True
                elif "<widget typeId" in line:
                    if check_for_border_prop and not found_border_prop:
                        fixed = True
                        result.append("   <border_color>\n")
                        result.append(
                            '     <color name="Canvas" red="200" green="200" blue="200"></color>\n'
                        )
                        result.append("   </border_color>\n")
                        result.append("   <border_style>0</border_style>\n")
                        # Reset
                        check_for_border_prop = False
                        found_border_prop = False
                        if (
                            "org.csstudio.opibuilder.widgets.groupingContainer" in line
                            and not check_for_border_prop
                        ):
                            check_for_border_prop = True
                if check_for_border_prop:
                    if "border_color" in line:
                        check_for_border_prop = False
                        found_border_prop = True
                result.append(line)
        if fixed:
            self.cs.fix_group_cont = True
            logger.debug(
                "OPI ERROR: Missing border property in 'Group' widget... fixing"
            )
            with open(self.tmp_file_path, "w") as f:
                f.writelines(result)

        return fixed

    def fix_action_open_macro(self, widget):
        actions = widget["actions"]["action"]
        if type(actions) is not list:
            actions = [actions]
        for action in actions:
            if action["@type"] == "open_display":
                if "macros" in action.keys():
                    for i in action["macros"]:
                        if action["macros"][i] == "$(name)":
                            self.cs.fix_action_macro_name = True
                            action["macros"][i] = widget["name"]

    def create_symbol_from_edm(self, widget):
        setup_dict = {}
        if self.template_file_path is None:
            logger.warning("Found edm symbol widget but could not convert it due to no template file being supplied.")
            return
        
        if not os.path.isfile(self.template_file_path):
            error_msg = f"No template file provided"
            logger.error(error_msg, exc_info=True)
            raise FileNotFoundError(error_msg)

        with open(self.template_file_path, "r", encoding="utf-8") as file:
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
                        self.cs.create_sym_images = True
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
                            # We look through the rules and see if we need to re-order any symbols
                            if rule["@prop_id"] == "image_index":
                                widget["symbols"]["symbol"] = self.reorder_widgets_from_rules(symbols, rule)

                            # Look for a rule which is used to change the displayed symbol to a symbol
                            # signifying an invalid state.
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
                            
                                # We must create a rule for each symbol specified for the widget which
                                # overwrites the displayed symbol widget with the special invalid state symbol.
                                for i in range(1, len(widget["symbols"]["symbol"])):
                                    # Copy dictionary to get a unique copy
                                    additional_rule = rule.copy()
                                    additional_rule["@name"] = rule["@name"] + f"_{i}"
                                    additional_rule["@prop_id"] = f"symbols[{i}]"
                                    additional_rules.append(additional_rule)
                        
                        # Extend the rules for this widget with the new rules we created
                        rules.extend(additional_rules)
                        widget["rules"]["rule"] = rules
                    
    def reorder_widgets_from_rules(self, symbols, rule):
        # Search through all boolean expressions and create a map between the PV value
        # and the symbol index to use.
        # We only bother to handle 2 cases,
        # - pvX == Y
        # - pvX >= Y && pvX < Z

        # Contains a list of tuples of (pv_val, symbol_index)
        reorder_map: list(tuple) = []
        try:
            if "exp" in rule:
                for e in rule["exp"]:
                    pv_val = None
                    result = int(e["expression"])
                    bool_logic = e["@bool_exp"]
                    bool_logic = bool_logic.replace(" ", "")
                    # Match for pvX in string
                    if re.findall(r'pv\d+', bool_logic):
                        if "==" in bool_logic:
                            match = re.search(r'==\s*(\d+)', bool_logic)
                            if match:
                                pv_val = int(match.group(1))
                        elif ">=" in bool_logic and "<" in bool_logic and "&&" in bool_logic:
                            # Gets the integer between >= and &&. This could be made smarter if required
                            match = re.search(r'>=\s*(.+?)\s*&&', bool_logic)
                            if match:
                                pv_val = int(float(match.group(1)))
                        reorder_map.append((pv_val, result))

        except (LookupError, ValueError):
            logger.warning("Failed to parse rule when attempting to reorder symbol widget.")

        # Sort the map by ascending pv_val
        reorder_map = sorted(reorder_map, key=lambda x: x[0])
        new_symbols_order = [symbol for symbol in symbols]
        for pv_val, index in reorder_map:
            for symbol in symbols:
                if pv_val >= len(new_symbols_order):
                    # Sometimes rules can specify a symbol to use for a pv_value
                    # outside the number of images, we handle this by adding it to the end
                    new_symbols_order.append(symbol)
                elif f"_{index}." in symbol:
                    new_symbols_order[pv_val] = symbol

        return new_symbols_order

    def parse_all_fields_in_dict(self, input_dict):
        for field in input_dict:
            if type(input_dict[field]) is dict:
                self.parse_all_fields_in_dict(input_dict[field])
            elif type(input_dict[field]) is list:
                for item in input_dict[field]:
                    if type(item) is dict:
                        self.parse_all_fields_in_dict(item)
                    else:
                        self.find_pv_function_in_field(input_dict, field)
            else:
                self.find_pv_function_in_field(input_dict, field)

    def find_pv_function_in_field(self, widget, field):
        # Some fields may contain lists
        if type(widget[field]) is list:
            for i in range(len(widget[field])):
                widget[field][i] = self.convert_pv_function(widget[field][i])
        else:
            widget[field] = self.convert_pv_function(widget[field])

    def convert_pv_function(self, inpString):
        if inpString is not None and "pv(" in inpString:
            pv_replacement = "".join([g if i==0 else g if (k := g.find('")'))<0 else "`"+g[:k]+"`"+g[k+2:] for (i,g) in enumerate(inpString.split('pv("'))])
            # Catch case where there is a function call nested within a pv(...) function
            # In this case the above replacement will not have found pv(" and so it
            # will still exist in the replacement. There is no way to handle this in Phoebus
            # so just issue warning
            if "pv(" in pv_replacement:
                logger.warning("Cannot fix the following formula in Phoebus "+inpString)
            else:
                logger.info("Replace pv() function with "+pv_replacement)
                return pv_replacement

        # Otherwise return the original
        return inpString

    def parse_widget(self, widget, spacing, level, parent):

        if not isinstance(widget, dict):
            return

        if "@typeId" in widget:
            logging.error(
                "Detected old CSS index '@typeid' - suggests that the Phoebus converter\
    failed to convert the GroupContainer widget.\nTry running converter with --fixGroup option."
            )
            return

        if widget["@type"] == "group":
            if "widget" in widget:
                if type(widget["widget"]) is not list:
                    self.parse_widget(widget["widget"], spacing + " ", level + 1, widget)
                else:
                    for w in widget["widget"]:
                        self.parse_widget(w, spacing + " ", level + 1, widget)
        elif widget["@type"] == "tabs":
            if "tabs" in widget:
                if "tab" in widget["tabs"]:
                    if type(widget["tabs"]["tab"]) is not list:
                        if type(widget["tabs"]["tab"]["children"]["widget"]) is not list:
                            self.parse_widget(widget["tabs"]["tab"]["children"]["widget"], spacing + " ", level + 1, widget)
                        else:
                            for child_widget in widget["tabs"]["tab"]["children"]["widget"]:
                                self.parse_widget(child_widget, spacing + " ", level + 1, widget)
                    else:
                        for tab in widget["tabs"]["tab"]:
                            if type(tab["children"]["widget"]) is not list:
                                self.parse_widget(tab["children"]["widget"], spacing + " ", level + 1, widget)
                            else:
                                for child_widget in tab["children"]["widget"]:
                                    self.parse_widget(child_widget, spacing + " ", level + 1, widget)
        elif widget["@type"] == "action_button":
            if "text" in widget:
                if (
                    widget["text"] == "EXIT"
                    or widget["text"] == "Exit"
                    or widget["text"] == "Cancel"
                ):
                    widget["actions"]["action"] = self.fix_exit_button()
            if widget["actions"] is not None: 
                self.process_widget_actions(widget)

        elif widget["@type"] == "symbol":
            if "actions" in widget:
                if (
                    widget["actions"] is not None
                    and "action" in widget["actions"]
                ):
                    self.replace_opi_extension(widget["actions"]["action"])
                    self.fix_action_open_macro(widget)
            self.create_symbol_from_edm(widget)
        elif widget["@type"] == "embedded":
            self.fix_embedded_screen_ext(widget)
        elif widget["@type"] == "progressbar":
            # Look for any progress bar widgets with alarm borders enabled
            alarm_sensitive_progress_bars = self.get_alarm_sensitive_progress_bars()
            if "name" in widget and "pv_name" in widget:
                if [widget["name"], widget["pv_name"]] in alarm_sensitive_progress_bars:
                    widget["border_alarm_sensitive"] = "true"
        elif widget["@type"] == "tank":
            # Phoebus is missing the <transparent_background> option, so we just set the background
            # colour to transparent
            transparent_tank_backgrounds = self.get_transparent_background_tank_widget()
            if "name" in widget and "pv_name" in widget:
                if [widget["name"], widget["pv_name"]] in transparent_tank_backgrounds:
                    widget["background_color"] = {'color': {'@name': 'Transparent', '@red': '255', '@green': '255', '@blue': '255'}}

        self.parse_all_fields_in_dict(widget)
        self.check_rule(widget)
        self.check_actions_in_non_action_buttons(widget)

    def modify_bob_xml(self):
        as_dict = {}
        with open(
            os.path.join(self.dst_dir_path, self.dst_filename), "r", encoding="utf-8"
        ) as file:
            fxml = file.read()

            as_dict = xmltodict.parse(fxml)
            try:
                widgets = as_dict["display"]["widget"]
            except KeyError as e:
                logger.error(f"Failed to parse xml for file: {self.src_file_path} with error:\n {e}")
                return None
            
            for w in widgets:
                self.parse_widget(w, "", 0, as_dict["display"])

        return as_dict

    def write_dict(self, as_dict):
        with open(os.path.join(self.dst_dir_path, self.dst_filename), "w") as f:
            new_xml = xmltodict.unparse(as_dict, pretty=True)
            f.write(new_xml)

    def run_pre_conversion_steps(self, fix_group):
        """Perform modifications to the .opi file before doing the main conversion
        to .bob using the Phoebus converter."""
        use_modified_opi = False
        use_modified_opi = self.replace_edm_symbol_widget()
        if fix_group:
            # Fix missing border items from grouping container
            if use_modified_opi:
                self.fix_grouping_container(self.tmp_file_path)
            else:
                use_modified_opi = self.fix_grouping_container(self.src_file_path)
        return use_modified_opi
    
    def run_post_conversion_steps(self, no_modify):
        """ 
            - Replaces EXIT scripts with an ActionButton to Exit
            - Action Buttons to open displays are modified to open .bob extensions
            - Rules using legacy severity are replaced
            - Flag that actions are running on non-action buttons
        """
        if not no_modify:
            xml_dict = self.modify_bob_xml()
            # Write out modified xml
            if xml_dict is not None:
                self.write_dict(xml_dict)
            else:
                # Dictionary could not be parsed
                return None

def log_conversion_steps(log_data):
    # Log what was done
    if log_data.replace_edm_sym:
        logger.info("Replaced EDMSymbol widgets in OPI before running converter")
    if log_data.fix_group_cont:
        logger.info(
            "Fixed Grouping Container widget is OPI that is missing required properties"
        )
    if log_data.update_leg_sev:
        logger.info("Updating legacy PV severity status")
    if log_data.fix_exit_but:
        logger.info(
            "Converting EXIT to script to an EXIT action button to close display"
        )
    if log_data.replace_opi_ext:
        logger.info(
            "Replaced .OPI file extensions with .BOB for EmbeddedDisplay/LinkingContainers/Open Display actions"
        )
    if log_data.non_ab_action:
        logger.warning(
            "Found an action on a widget that is NOT an ActionButton or Symbol widget. Debug for more"
        )
    if log_data.replace_with_ab:
        logger.info(
            "Replaced a Rectangle/BooleanButton widget with an action with an Action Button widget"
        )
    if log_data.replace_db_script:
        logger.info(
            "Replaced script to open databrowser with an action to open a DataBrowser plt file"
        )
    if log_data.fix_action_macro_name:
        logger.info(
            "Fixed Open Display action that contains the $name macro that does not get parsed"
        )
    if log_data.create_sym_images:
        logger.info("Created new images for Symbol widget from original")
    if log_data.replace_action_tab:
        logger.info("Replace open display target=tab with target=standalone")


def parse_args():
    # Conversion options
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--src_file", required=True, help="Source opi file")
    ap.add_argument(
        "-d", "--dst_dir", required=True, help="Directory to place converted bob file"
    )
    ap.add_argument("-t", "--tfile", required=False, help="Template file")
    ap.add_argument(
        "-p", "--pname", required=False, help="Databrowser plot file to open in action"
    )
    ap.add_argument("--fix_group", action="store_true", help="Fix grouping container")
    ap.add_argument(
        "--no_modify",
        action="store_true",
        help="Don't modify anything after the Phoebus conversion",
    )
    ap.add_argument(
        "--replace_tab",
        action="store_true",
        help="Replace actions that open in tabs to open in standalone",
    )
    ap.add_argument(
        "--no_edit_file",
        action="store_true",
        help="File describing opi files that shouldnt be converted.",
    )
    ap.add_argument(
        "--debug",
        help="Enable debug logging",
        action="store_true",
        default=False,
    )
    args = ap.parse_args()

    src_file_path = Path(args.src_file)
    dst_dir_path = Path(args.dst_dir)

    if args.tfile is not None:
        template_file_path = Path(args["tfile"])

    if args.debug:
        logger.setLevel(logging.DEBUG)

    return (
        src_file_path,
        dst_dir_path,
        template_file_path,
        args.pname,
        args.fix_group,
        args.no_modify,
        args.replace_tab,
        args.no_edit_file,
    )


def main(
    src_file_path,
    dst_dir_path,
    dst_filename=None,
    template_file_path=None,
    fix_group=True,
    no_modify=False,
    replace_tab=False,
    no_edit_file=None,
) -> Path | None:
    if dst_filename is None:
        dst_filename = src_file_path.name.replace(".opi", ".bob")

    tmp_file_path = dst_dir_path / "tmp.opi"

    sc = ScreenConverter(
        src_file_path,
        dst_filename,
        dst_dir_path,
        tmp_file_path,
        template_file_path,
        replace_tab,
    )

    # Check the no_edit file to see if we should even run the conversion
    # Instead of doing it like this, we could read a comment at the top of the bob file
    if no_edit_file is not None:
        with open(no_edit_file, "r") as f:
            lines = f.readlines()
            for line in lines:
                if src_file_path == line.strip():
                    logging.warning(
                        "!!! OPI file to be converted is in the 'no_edit' list suggesting \
                    that it has had manual changes that should not be overwritten.\n\
                    If this is incorrect then remove this file from the "
                        + no_edit_file
                        + ".\n\
                    Skipping this conversion"
                    )
                    return None

    # If conversion has already been run, delete previous BOB conversion
    sc.delete_old_file()

    # Modify the OPI file before running conversion
    use_modified_opi = sc.run_pre_conversion_steps(fix_group)

    # Should we use the modified OPI files
    if not use_modified_opi:
        # Copy the src file to the tmp location overwriting any existing tmp.opi. This is done
        # as autoconverting directly from the src file sometimes fails due to read permission issues
        shutil.copy(src_file_path, tmp_file_path)

    # Run Phoebus converter
    conversion_success = sc.run_converter(tmp_file_path)

    # Delete tmp.opi
    os.remove(tmp_file_path)

    if not conversion_success:
        return None
    
    # Rename tmp.bob to the required name
    new_file = os.path.join(dst_dir_path, dst_filename)
    tmp_file_path.with_suffix(".bob").rename(new_file)

    # Make modifications to converted .bob file
    sc.run_post_conversion_steps(no_modify)

    log_data = sc.cs
    log_conversion_steps(log_data)
    return Path(new_file)


if __name__ == "__main__":
    main(*parse_args())
