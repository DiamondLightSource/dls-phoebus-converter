import subprocess
import os
import xmltodict
import pprint
import argparse

# Script params
phoebus = "/dls_sw/apps/phoebus/dls_config/phoebus.sh"
no_edit_file = "no_edit.txt"

debug = False


# Conversion options
ap = argparse.ArgumentParser()
ap.add_argument("-f", "--file", required=True, help="opi file")
ap.add_argument("-t", "--tfile", required=False, help="Template file")
ap.add_argument("-p", "--pname", required=False, help="Databrowser plot file to open in action")
ap.add_argument("--fixGroup", action="store_true", help="Fix grouping container")
ap.add_argument("--nomodify", action="store_true", help="Don't modify anything after the Phoebus conversion")
ap.add_argument("--replaceTab", action="store_true", help="Replace actions that open in tabs to open in standalone")
args = vars(ap.parse_args())

infile = args["file"]
outdir = "/".join(infile.split("/")[:-1])+"/"
tmpfile = outdir + "tmp.opi"
template_file = "/test/"
if args["tfile"] != None:
    template_file = args["tfile"]

outfile = outdir + infile.split("/")[-1].replace(".opi",".bob")

plot_loc_macro = "$(PLOT_LOC)"


mydict = {}
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



def replaceEdmSymbolWidget():
    result = []
    with open(infile, "r") as f:
        lines = f.readlines()
        checkForBorderProp = False
        foundBorderProp = False
        fixed = False
        for line in lines:
            if "org.csstudio.opibuilder.widgets.edm.symbolwidget" in line:
                line = line.replace("org.csstudio.opibuilder.widgets.edm.symbolwidget","org.csstudio.opibuilder.widgets.symbol.multistate.MultistateMonitorWidget")
                fixed = True
            result.append(line)
    if fixed:
        global replaceEdmSym
        replaceEdmSym = True
        if debug:
            print("-> Replacing CSS EDM Widgets in OPI before conversion")
        with open(tmpfile, "w") as f:
            f.writelines(result)

    return fixed


def deleteOldFile():
    try:
        os.remove(outfile)
        if debug:
            print("-> Removing old conversion: "+outfile)
    except OSError:
        pass

def runConverter(file):
    convert_command = phoebus+"\
     -main org.csstudio.display.builder.model.Converter -output "+outdir+" "+file
    process = subprocess.Popen(convert_command.split(),
                     stdout=subprocess.PIPE, 
                     stderr=subprocess.PIPE)

    stdout, stderr = process.communicate()
    #print(stdout)
    for l in stderr.decode("utf-8").split("/n"):
        if debug:
            print(l)

def updateLegacySevStatus(inputField, legSev, newSev):
    if legSev in inputField:
        global updateLegSev
        updateLegSev = True
        result = inputField.replace(legSev, newSev)
        if debug:
            print(" -> Fixing "+legSev+" to "+newSev)
        return result
    else:
        return inputField

def checkLegacySev(inputField):
    # OK, Major, Minor, Invalid/undefined
    legacy = ["pvLegacySev0==0", "pvLegacySev0==1", "pvLegacySev0==2", "pvLegacySev0==-1"]
    newV = ["pvSev0==0", "pvSev0==2", "pvSev0==1", "pvSev0==3"]
    result = inputField
    for i in range(len(legacy)):
        result = updateLegacySevStatus(result, legacy[i], newV[i])       
    return result

def checkRule(widget):
    if "rules" in widget:
        if type(widget["rules"]["rule"]) is list:
            for r in widget["rules"]["rule"]:
                ruleExpr = r["exp"]
                if type(ruleExpr) == list:
                    for e in ruleExpr:
                        e["@bool_exp"] = checkLegacySev(e["@bool_exp"])
                else:
                    ruleExpr["@bool_exp"] = checkLegacySev(ruleExpr["@bool_exp"])
        else:
            ruleExpr = widget["rules"]["rule"]["exp"]
            if type(ruleExpr) is list:
                for r in ruleExpr:
                    r["@bool_exp"] = checkLegacySev(r["@bool_exp"])
            else:
                ruleExpr["@bool_exp"] = checkLegacySev(ruleExpr["@bool_exp"])


def fixExitButton():
    global fixExitBut
    fixExitBut = True
    newaction = {}
    newaction["@type"] = "close_display"
    newaction["description"] = "Close display"
    return newaction

def replaceOpiExtenstion(action):
    if "file" in action:
        global replaceOpiExt
        replaceOpiExt = True
        if debug:
            print("-> Replacing file open action to open .BOB")
        opi = action["file"]
        bob = opi.replace(".opi", ".bob")
        action["file"] = bob


def replaceOpenInTab(actions):
    global replaceActionTab
    if type(actions["action"]) == list:
        acts = actions["action"]
    else:
        acts = [actions["action"]]
    for action in acts:
        if action["@type"] == "open_display":
            if action["target"] == "tab":
                action["target"] = "standalone"
                replaceActionTab = True


def checkActionsInNonActionButtons(widget):
    if "actions" in widget:
        if widget["actions"] != None and widget["@type"] != "action_button" and widget["@type"] != "symbol":
            global nonABAction
            nonABAction = True
            if debug:
                print("-> !!!!!!! WARNING: Action contained in widget that isn't an action button: "+str(widget["@type"])+", name: "+str(widget["name"]))
                print("    action: "+str(widget["actions"]["action"]))
            if widget["@type"] == "rectangle" or widget["@type"] == "bool_button":
                if widget["@type"] == "bool_button":
                    if widget["on_label"] != widget["off_label"]:
                        return
                global replaceWithAB
                replaceWithAB = True
                if debug:
                    print("  Attempting to fix by converting to an action_button")
                widget["@type"] = "action_button"

                if "on_label" in widget:
                    widget["text"] = widget["on_label"]
                else:
                    widget["text"] = ""
                if "rules" in widget:
                    if type(widget["rules"]["rule"]) == list:
                        for r in widget["rules"]["rule"]:
                            if r["@prop_id"] == "line_color":
                                widget["rules"]["rule"].remove(r)
                    else:
                        if widget["rules"]["rule"]["@prop_id"] == "line_color":
                                widget["rules"]["rule"].remove(r)



def replaceDataBrowserScript(widget):
    if debug:
        print("-> Replacing databrowser")
    if widget["text"] == "Graph":
        action = widget["actions"]["action"]
        if action["@type"] == "execute":
            global replaceDBScript
            replaceDBScript = True
            action["@type"] = "open_file"
            action["description"] = "Open File"
            action["file"] = plot_loc_macro+args["pname"]+".plt"
            del action["script"] 


def fixEmbeddedScreenExt(widget):
    if "file" not in widget:
        return
    global replaceOpiExt
    replaceOpiExt = True
    opi_file = widget["file"]
    bob_file = opi_file.replace(".opi", ".bob")
    widget["file"] = bob_file


def fixGroupingContainer(opifile):
    result = []
    with open(opifile, "r") as f:
        lines = f.readlines()
        checkForBorderProp = False
        foundBorderProp = False
        fixed = False
        for line in lines:
            if "org.csstudio.opibuilder.widgets.groupingContainer" in line and not checkForBorderProp:
                checkForBorderProp = True
            elif "<widget typeId" in line:
                if checkForBorderProp and not foundBorderProp:
                    fixed = True
                    result.append("   <border_color>\n")
                    result.append('     <color name="Canvas" red="200" green="200" blue="200"></color>\n')
                    result.append("   </border_color>\n")
                    result.append("   <border_style>0</border_style>\n")
                    # Reset
                    checkForBorderProp = False
                    foundBorderProp = False
                    if "org.csstudio.opibuilder.widgets.groupingContainer" in line and not checkForBorderProp:
                        checkForBorderProp = True
            if checkForBorderProp:
                if "border_color" in line:
                    checkForBorderProp = False
                    foundBorderProp = True
           
            result.append(line)
    if fixed:
        global fixGroupCont
        fixGroupCont = True
        if debug:
            print("-> OPI ERROR: Missing border property in 'Group' widget... fixing")
        with open(tmpfile, "w") as f:
            f.writelines(result)

    return fixed


def fixActionOpenMacro(widget):
    action = widget["actions"]["action"]
    if action["@type"] == "open_display":
        for i in action["macros"]:
            if action["macros"][i] == "$(name)":
                global fixActionMacroName
                fixActionMacroName = True
                action["macros"][i] = widget["name"]

def createSymbolFromEdm(widget):
    setup_dict = {}
    if not os.path.isfile(template_file):
        print("!!!! No template files provided!! Exiting")
        exit(-1)
    with open(template_file, 'r', encoding='utf-8') as file:
        fxml = file.read()

        setup_dict = xmltodict.parse(fxml)

        sym_list = []
        if type(setup_dict["symbols"]["symbol"]) != list:
            sym_list = [setup_dict["symbols"]["symbol"]]
        else:
            sym_list = setup_dict["symbols"]["symbol"]
        for s in sym_list:
            name = s["name"]
            if s["name"] == widget["name"]:
                if debug:
                    print("-> Fixing Symbol widget with name: "+s["name"])
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
                ext = "."+location.split(".")[-1]
                if debug:
                    print("-> Creating new images for symbol from: "+location)
                if os.path.isfile(outimage[0]+"_0"+ext):
                    # Skip if it alreayd exists
                    if debug:
                        print("   ... images already exist - skipping")
                else:
                    global createSymImages
                    createSymImages = True
                    for n in range(nimages):
                        output = outimage[0]+"_"+str(n)+ext
                        x = 0 + width*n
                        cmd =  "convert " + location + " -crop "+str(width)+"x"+str(height)+"+"+str(x)+"+0 "+output
                        process = subprocess.Popen(cmd.split(),
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)

                        stdout, stderr = process.communicate()

                outimage = ".".join(image.split(".")[:-1])
                ext = "."+image.split(".")[-1]
                symbols = []
                startindexlist = startindex.split(",")
                if len(startindexlist) > 1:
                    for n in startindexlist:
                        symbols.append(outimage+"_"+n+ext)
                else:
                    for n in range(nimages-int(startindexlist[0])):
                        index = n + int(startindexlist[0])
                        symbols.append(outimage+"_"+str(index)+ext)

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
                            exp["value"] = outimage + "_" + str(invalidimageindex)+ext

                    rule["exp"] = exp


def parseWidget(widget, spacing, level, parent):
    #print(str(level)+ " " + spacing + widget["@type"] + ": " + widget["name"])

    if not isinstance(widget, dict):
        return

    if "@typeId" in widget:
        print("-> Detected old CSS index '@typeid' - suggests that the Phoebus converter\
failed to convert the GroupContainer widget.\nTry running converter with --fixGroup option.")
        exit(0)

    if widget["@type"] == "group":
        if type(widget["widget"]) is not list:
            parseWidget(widget["widget"], spacing+" ", level+1, widget)
        else:
            for w in widget["widget"]:
                parseWidget(w, spacing+" ", level+1, widget)
    elif widget["@type"] == "action_button" :
        if "text" in widget:
            if widget["text"] == "EXIT" or widget["text"] == "Exit" or widget["text"] == "Cancel":
                widget["actions"]["action"] = fixExitButton()
        replaceOpiExtenstion(widget["actions"]["action"])
        replaceDataBrowserScript(widget)
        if args["replaceTab"]:
            replaceOpenInTab(widget["actions"])
    elif widget["@type"] == "symbol":
        if "actions" in widget:
            if widget["actions"] != None:
                replaceOpiExtenstion(widget["actions"]["action"])
                fixActionOpenMacro(widget)
        createSymbolFromEdm(widget)
    elif widget["@type"] == "embedded":
        fixEmbeddedScreenExt(widget)

    checkRule(widget)
    checkActionsInNonActionButtons(widget)

def modifyBobXml():
    as_dict = {}
    with open(outfile, 'r', encoding='utf-8') as file:
        fxml = file.read()

        as_dict = xmltodict.parse(fxml)
        widgets = as_dict["display"]["widget"]
        for w in widgets:
            parseWidget(w, "", 0, as_dict["display"])

    return as_dict

def writeDict(as_dict, xml_dict): 
    with open(outfile, "w") as f:
        new_xml = xmltodict.unparse(as_dict,pretty=True)
        f.write(new_xml)
        #pprint.pprint(as_dict["display"]["widget"], indent=2)
      

def main():
    # Check the no_edit file to see if we should even run the conversion
    with open(no_edit_file, "r") as f:
        lines = f.readlines()
        for line in lines:
            if infile == line.strip():
                print("!!! OPI file to be converted is in the 'no_edit' list suggesting \
    that it has had manual changes that should not be overwritten.\n\
    If this is incorrect then remove this file from the "+no_edit_file+".\n\
    Exiting...")
                exit(0)

    use_tmp_file = False
    # Modify the OPI file before running conversion
    use_tmp_file = replaceEdmSymbolWidget()

    if args["fixGroup"]:
        # Fix missing border items from grouping container
        if use_tmp_file:
            fixGroupingContainer(tmpfile)
        else:
            use_tmp_file = fixGroupingContainer(infile)    

    # If conversion has already been run, delete previous BOB conversion
    deleteOldFile()

    file = infile
    # Should we used the modified OPI files
    if use_tmp_file:
        file = tmpfile

    # Run Phoebus converter
    runConverter(file)

    # Remove tmp OPI files if a modified version was created
    if use_tmp_file:
        os.rename(tmpfile.replace(".opi",".bob"), outfile)
        #os.remove(tmpfile)

    if not args["nomodify"]:
        """ 
            - Replaces EXIT scripts with an ActionButton to Exit
            - Action Buttons to open displays are modified to open .bob extensions
            - Rules using legacy severity are replaced
            - Flag that actions are running on non-action buttons
        """
        xml_dict = modifyBobXml()
        # Write out modified xml
        writeDict(xml_dict, xml_dict)

    # Log what was done
    if replaceEdmSym:
        print("-> Replaced EDMSymbol widgets in OPI before running converter")
    if fixGroupCont:
        print("-> Fixed Grouping Container widget is OPI that is missing required properties")
    if updateLegSev:
        print("-> Updating legacy PV severity status")
    if fixExitBut:
        print("-> Converting EXIT to script to an EXIT action button to close display")
    if replaceOpiExt:
        print("-> Replaced .OPI file extensions with .BOB for EmbeddedDisplay/LinkingContainers/Open Display actions")
    if nonABAction:
        print("-> Found an action on a widget that is NOT an ActionButton or Symbol widget. Debug for more")
    if replaceWithAB:
        print("-> Replaced a Rectangle/BooleanButton widget with an action with an Action Button widget")
    if replaceDBScript:
        print("-> Replaced script to open databrowser with an action to open a DataBrowser plt file")
    if fixActionMacroName:
        print("-> Fixed Open Display action that contains the $name macro that does not get parsed")
    if createSymImages:
        print("-> Created new images for Symbol widget from original")
    if replaceActionTab:
        print("-> Replace open display target=tab with target=standalone")

if __name__ == "__main__":
    main()
