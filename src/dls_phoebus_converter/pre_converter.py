"""Conversion steps which are required before running the phoebus converter"""

import logging

from dls_phoebus_converter.logconfig import setup_logging

if not logging.getLogger("dls_phoebus_converter"):
    setup_logging()
logger = logging.getLogger("dls_phoebus_converter")


def pre_conversion_steps(fix_group, tmp_file_path, src_file_path):
    use_modified_opi = False
    use_modified_opi = replace_edm_symbol_widget(src_file_path)
    if fix_group:
        # Fix missing border items from grouping container
        if use_modified_opi:
            fix_grouping_container(tmp_file_path)
        else:
            use_modified_opi = fix_grouping_container(src_file_path)
    return use_modified_opi


def replace_edm_symbol_widget(src_file_path):
    result = []
    with open(src_file_path) as f:
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


def fix_grouping_container(opi_file_path):
    result = []
    with open(opi_file_path) as f:
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
                        '     <color name="Canvas" red="200" green="200" blue="200"></color>\n'  # noqa: E501
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
        logger.debug("OPI ERROR: Missing border property in 'Group' widget... fixing")
        with open(self.tmp_file_path, "w") as f:
            f.writelines(result)

    return fixed
