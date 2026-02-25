from pathlib import Path
import subprocess
import os
import xmltodict
import argparse
from dataclasses import dataclass


PHOEBUS_SH_FILE = "/dls_sw/apps/phoebus/dls_config/phoebus.sh"
PLOT_LOCATION_MACRO = "$(PLOT_LOC)"
TEMPLATE_FILE = "templates/example_template.xml"


@dataclass
class ConversionSteps:
    replaceEdmSym = False
    fixGroupCont = False
    updateLegSev = False
    fixExitBut = False
    replaceOpiExt = False
    nonABAction = False
    replaceWithAB = False
    replaceDBScript = False
    fixOpenActionName = False
    fixActionMacroName = False
    createSymImages = False
    replaceActionTab = False


class ScreenConverter:
    def __init__(
        self,
        src_file,
        dst_file,
        dst_dir,
        tmp_file,
        template_file,
        debug,
        pname,
        replace_tab,
    ):
        self.src_file = src_file
        self.dst_file = dst_file
        self.dst_dir = dst_dir
        self.tmp_file = tmp_file
        self.template_file = template_file
        self.debug = debug
        self.pname = pname
        self.replace_tab = replace_tab
        self.cs = ConversionSteps()

    def replace_edm_symbol_widget(self):
        result = []
        with open(self.src_file, "r") as f:
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
            self.cs.replaceEdmSym = True
            if self.debug:
                print("-> Replacing CSS EDM Widgets in OPI before conversion")
            with open(self.tmp_file, "w") as f:
                f.writelines(result)

        return fixed

    def delete_old_file(self):
        try:
            os.remove(self.dst_file)
            if self.debug:
                print("-> Removing old conversion: " + self.dst_file)
        except OSError:
            pass

    def run_converter(self, file):
        convert_command = (
            PHOEBUS_SH_FILE
            + "\
        -main org.csstudio.display.builder.model.Converter -output "
            + str(self.dst_dir)
            + " "
            + str(file)
        )
        process = subprocess.Popen(
            convert_command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        stdout, stderr = process.communicate()
        # print(stdout)
        for line in stderr.decode("utf-8").split("/n"):
            if self.debug:
                print(line)

    def update_legacy_sev_status(self, inputField, legSev, newSev):
        if legSev in inputField:
            self.cs.updateLegSev = True
            result = inputField.replace(legSev, newSev)
            if self.debug:
                print(" -> Fixing " + legSev + " to " + newSev)
            return result
        else:
            return inputField

    def check_legacy_sev(self, inputField):
        # OK, Major, Minor, Invalid/undefined
        legacy = [
            "pvLegacySev0==0",
            "pvLegacySev0==1",
            "pvLegacySev0==2",
            "pvLegacySev0==-1",
        ]
        newV = ["pvSev0==0", "pvSev0==2", "pvSev0==1", "pvSev0==3"]
        result = inputField
        for i in range(len(legacy)):
            result = self.update_legacy_sev_status(result, legacy[i], newV[i])
        return result

    def check_rule(self, widget):
        if "rules" in widget:
            if type(widget["rules"]["rule"]) is list:
                for r in widget["rules"]["rule"]:
                    ruleExpr = r["exp"]
                    if type(ruleExpr) is list:
                        for e in ruleExpr:
                            e["@bool_exp"] = self.check_legacy_sev(e["@bool_exp"])
                    else:
                        ruleExpr["@bool_exp"] = self.check_legacy_sev(
                            ruleExpr["@bool_exp"]
                        )
            else:
                ruleExpr = widget["rules"]["rule"]["exp"]
                if type(ruleExpr) is list:
                    for r in ruleExpr:
                        r["@bool_exp"] = self.check_legacy_sev(r["@bool_exp"])
                else:
                    ruleExpr["@bool_exp"] = self.check_legacy_sev(ruleExpr["@bool_exp"])

    def fix_exit_button(self):
        self.cs.fixExitBut = True
        newaction = {}
        newaction["@type"] = "close_display"
        newaction["description"] = "Close display"
        return newaction

    def replace_opi_extension(self, action):
        if "file" in action:
            self.cs.replaceOpiExt = True
            if self.debug:
                print("-> Replacing file open action to open .BOB")
            opi = action["file"]
            bob = opi.replace(".opi", ".bob")
            action["file"] = bob

    def replace_open_in_tab(self, actions):
        if type(actions["action"]) is list:
            acts = actions["action"]
        else:
            acts = [actions["action"]]
        for action in acts:
            if action["@type"] == "open_display":
                if action["target"] == "tab":
                    action["target"] = "standalone"
                    self.cs.replaceActionTab = True

    def check_actions_in_non_action_buttons(self, widget):
        if "actions" in widget:
            if (
                widget["actions"] is not None
                and widget["@type"] != "action_button"
                and widget["@type"] != "symbol"
            ):
                self.cs.nonABAction = True
                if self.debug:
                    print(
                        "-> !!!!!!! WARNING: Action contained in widget that isn't an action button: "
                        + str(widget["@type"])
                        + ", name: "
                        + str(widget["name"])
                    )
                    print("    action: " + str(widget["actions"]["action"]))
                if widget["@type"] == "rectangle" or widget["@type"] == "bool_button":
                    if widget["@type"] == "bool_button":
                        if widget["on_label"] != widget["off_label"]:
                            return
                    self.cs.replaceWithAB = True
                    if self.debug:
                        print("  Attempting to fix by converting to an action_button")
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

    def replace_data_browser_script(self, widget):
        if self.debug:
            print("-> Replacing databrowser")
        if widget["text"] == "Graph":
            action = widget["actions"]["action"]
            if action["@type"] == "execute":
                self.cs.replaceDBScript = True
                action["@type"] = "open_file"
                action["description"] = "Open File"
                action["file"] = PLOT_LOCATION_MACRO + self.pname + ".plt"
                del action["script"]

    def fix_embedded_screen_ext(self, widget):
        if "file" not in widget:
            return
        self.cs.replaceOpiExt = True
        opi_file = widget["file"]
        bob_file = opi_file.replace(".opi", ".bob")
        widget["file"] = bob_file

    def fix_grouping_container(self, opifile):
        result = []
        with open(opifile, "r") as f:
            lines = f.readlines()
            checkForBorderProp = False
            foundBorderProp = False
            fixed = False
            for line in lines:
                if (
                    "org.csstudio.opibuilder.widgets.groupingContainer" in line
                    and not checkForBorderProp
                ):
                    checkForBorderProp = True
                elif "<widget typeId" in line:
                    if checkForBorderProp and not foundBorderProp:
                        fixed = True
                        result.append("   <border_color>\n")
                        result.append(
                            '     <color name="Canvas" red="200" green="200" blue="200"></color>\n'
                        )
                        result.append("   </border_color>\n")
                        result.append("   <border_style>0</border_style>\n")
                        # Reset
                        checkForBorderProp = False
                        foundBorderProp = False
                        if (
                            "org.csstudio.opibuilder.widgets.groupingContainer" in line
                            and not checkForBorderProp
                        ):
                            checkForBorderProp = True
                if checkForBorderProp:
                    if "border_color" in line:
                        checkForBorderProp = False
                        foundBorderProp = True

                result.append(line)
        if fixed:
            self.cs.fixGroupCont = True
            if self.debug:
                print(
                    "-> OPI ERROR: Missing border property in 'Group' widget... fixing"
                )
            with open(self.tmp_file, "w") as f:
                f.writelines(result)

        return fixed

    def fix_action_open_macro(self, widget):
        action = widget["actions"]["action"]
        if action["@type"] == "open_display":
            if "macros" in action.keys():
                for i in action["macros"]:
                    if action["macros"][i] == "$(name)":
                        self.cs.fixActionMacroName = True
                        action["macros"][i] = widget["name"]

    def create_symbol_from_edm(self, widget):
        setup_dict = {}
        if not os.path.isfile(self.template_file):
            print("Error!!!! No template files provided!!")
        with open(self.template_file, "r", encoding="utf-8") as file:
            fxml = file.read()

            setup_dict = xmltodict.parse(fxml)

            sym_list = []
            if type(setup_dict["symbols"]["symbol"]) is not list:
                sym_list = [setup_dict["symbols"]["symbol"]]
            else:
                sym_list = setup_dict["symbols"]["symbol"]
            for s in sym_list:
                if s["name"] == widget["name"]:
                    if self.debug:
                        print("-> Fixing Symbol widget with name: " + s["name"])
                    image = s["image"]
                    location = s["location"]
                    width = int(s["width"])
                    height = int(s["height"])
                    nimages = int(s["nimages"])
                    startindex = s["startindex"]
                    invalidimageindex = int(s["invalidimageindex"])

                    # Run action of left click
                    if "actions" in widget:
                        widget["run_actions_on_mouse_click"] = "true"

                    # Set up symbols
                    outimage = location.split(".")[:-1]
                    ext = "." + location.split(".")[-1]
                    if self.debug:
                        print("-> Creating new images for symbol from: " + location)
                    if os.path.isfile(outimage[0] + "_0" + ext):
                        # Skip if it alreayd exists
                        if self.debug:
                            print("   ... images already exist - skipping")
                    else:
                        self.cs.createSymImages = True
                        for n in range(nimages):
                            output = outimage[0] + "_" + str(n) + ext
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

                    outimage = ".".join(image.split(".")[:-1])
                    ext = "." + image.split(".")[-1]
                    symbols = []
                    startindexlist = startindex.split(",")
                    if len(startindexlist) > 1:
                        for n in startindexlist:
                            symbols.append(outimage + "_" + n + ext)
                    else:
                        for n in range(nimages - int(startindexlist[0])):
                            index = n + int(startindexlist[0])
                            symbols.append(outimage + "_" + str(index) + ext)

                    widget["symbols"]["symbol"] = symbols

                    # Fix rules
                    rule = widget["rules"]["rule"]
                    if rule["@prop_id"] == "image_index":
                        rule["@prop_id"] = "symbols[0]"
                        rule["@out_exp"] = "false"
                        exp = {}
                        for e in rule["exp"]:
                            if e["@bool_exp"] == "pvLegacySev0==-1":
                                exp["@bool_exp"] = "pvSev0==3 || pvSev0==4"
                                exp["value"] = (
                                    outimage + "_" + str(invalidimageindex) + ext
                                )

                        rule["exp"] = exp

    def parse_widget(self, widget, spacing, level, parent):
        # print(str(level)+ " " + spacing + widget["@type"] + ": " + widget["name"])

        if not isinstance(widget, dict):
            return

        if "@typeId" in widget:
            print(
                "-> Detected old CSS index '@typeid' - suggests that the Phoebus converter\
    failed to convert the GroupContainer widget.\nTry running converter with --fixGroup option."
            )
            exit(0)

        if widget["@type"] == "group":
            if type(widget["widget"]) is not list:
                self.parse_widget(widget["widget"], spacing + " ", level + 1, widget)
            else:
                for w in widget["widget"]:
                    self.parse_widget(w, spacing + " ", level + 1, widget)
        elif widget["@type"] == "action_button":
            if "text" in widget:
                if (
                    widget["text"] == "EXIT"
                    or widget["text"] == "Exit"
                    or widget["text"] == "Cancel"
                ):
                    widget["actions"]["action"] = self.fix_exit_button()
            self.replace_opi_extension(widget["actions"]["action"])
            self.replace_data_browser_script(widget)
            if self.replace_tab:
                self.replace_open_in_tab(widget["actions"])
        elif widget["@type"] == "symbol":
            if "actions" in widget:
                if widget["actions"] is not None:
                    self.replace_opi_extension(widget["actions"]["action"])
                    self.fix_action_open_macro(widget)
            self.create_symbol_from_edm(widget)
        elif widget["@type"] == "embedded":
            self.fix_embedded_screen_ext(widget)

        self.check_rule(widget)
        self.check_actions_in_non_action_buttons(widget)

    def modify_bob_xml(self):
        as_dict = {}
        with open(self.dst_file, "r", encoding="utf-8") as file:
            fxml = file.read()

            as_dict = xmltodict.parse(fxml)
            widgets = as_dict["display"]["widget"]
            for w in widgets:
                self.parse_widget(w, "", 0, as_dict["display"])

        return as_dict

    def write_dict(self, as_dict, xml_dict):
        with open(self.dst_file, "w") as f:
            new_xml = xmltodict.unparse(as_dict, pretty=True)
            f.write(new_xml)


def log_conversion_steps(log_data):
    # Log what was done
    if log_data.replaceEdmSym:
        print("-> Replaced EDMSymbol widgets in OPI before running converter")
    if log_data.fixGroupCont:
        print(
            "-> Fixed Grouping Container widget is OPI that is missing required properties"
        )
    if log_data.updateLegSev:
        print("-> Updating legacy PV severity status")
    if log_data.fixExitBut:
        print("-> Converting EXIT to script to an EXIT action button to close display")
    if log_data.replaceOpiExt:
        print(
            "-> Replaced .OPI file extensions with .BOB for EmbeddedDisplay/LinkingContainers/Open Display actions"
        )
    if log_data.nonABAction:
        print(
            "-> Found an action on a widget that is NOT an ActionButton or Symbol widget. Debug for more"
        )
    if log_data.replaceWithAB:
        print(
            "-> Replaced a Rectangle/BooleanButton widget with an action with an Action Button widget"
        )
    if log_data.replaceDBScript:
        print(
            "-> Replaced script to open databrowser with an action to open a DataBrowser plt file"
        )
    if log_data.fixActionMacroName:
        print(
            "-> Fixed Open Display action that contains the $name macro that does not get parsed"
        )
    if log_data.createSymImages:
        print("-> Created new images for Symbol widget from original")
    if log_data.replaceActionTab:
        print("-> Replace open display target=tab with target=standalone")


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
    args = ap.parse_args()

    src_file = Path(args.src_file)
    dst_dir = Path(args.dst_dir)

    if args.tfile is not None:
        template_file = Path(args["tfile"])
    else:
        template_file = TEMPLATE_FILE

    return src_file, dst_dir, template_file, args.pname, args.fix_group, args.no_modify, args.replace_tab, args.no_edit_file,
    


def main(
    src_file,
    dst_dir,
    template_file=TEMPLATE_FILE,
    debug=False,
    pname=None,
    fix_group=True,
    no_modify=False,
    replace_tab=False,
    no_edit_file=None,
) -> Path:
    dst_file = dst_dir / src_file.name.replace(".opi", ".bob")
    tmp_file = dst_dir / "tmp.opi"

    sc = ScreenConverter(
        src_file, dst_file, dst_dir, tmp_file, template_file, debug, pname, replace_tab
    )

    # Check the no_edit file to see if we should even run the conversion
    # Instead of doing it like this, we could read a comment at the top of the bob file
    if no_edit_file is not None:
        with open(no_edit_file, "r") as f:
            lines = f.readlines()
            for line in lines:
                if src_file == line.strip():
                    print(
                        "!!! OPI file to be converted is in the 'no_edit' list suggesting \
                    that it has had manual changes that should not be overwritten.\n\
                    If this is incorrect then remove this file from the "
                        + no_edit_file
                        + ".\n\
                    Exiting..."
                    )
                    exit(0)

    use_tmp_file = False
    # Modify the OPI file before running conversion
    use_tmp_file = sc.replace_edm_symbol_widget()

    if fix_group:
        # Fix missing border items from grouping container
        if use_tmp_file:
            sc.fix_grouping_container(tmp_file)
        else:
            use_tmp_file = sc.fix_grouping_container(src_file)

    # If conversion has already been run, delete previous BOB conversion
    sc.delete_old_file()

    file = src_file
    # Should we use the modified OPI files
    if use_tmp_file:
        file = tmp_file

    # Run Phoebus converter
    sc.run_converter(file)

    # Remove tmp OPI files if a modified version was created
    if use_tmp_file:
        tmp_file.with_suffix(".bob").rename(dst_file)
        os.remove(tmp_file)

    if not no_modify:
        """ 
            - Replaces EXIT scripts with an ActionButton to Exit
            - Action Buttons to open displays are modified to open .bob extensions
            - Rules using legacy severity are replaced
            - Flag that actions are running on non-action buttons
        """
        xml_dict = sc.modify_bob_xml()
        # Write out modified xml
        sc.write_dict(xml_dict, xml_dict)

    log_data = sc.cs
    log_conversion_steps(log_data)
    return sc.dst_file

if __name__ == "__main__":
    main(*parse_args())
