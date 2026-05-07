"""Handles the conversion of an individual file from opi to bob"""

import argparse
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dls_phoebus_converter.logconfig import setup_logging
from dls_phoebus_converter.post_converter import post_conversion_steps
from dls_phoebus_converter.pre_converter import pre_conversion_steps
from dls_phoebus_converter.screen_converter import ConversionConfig

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


class OpiConverter:
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

    def run_pre_conversion_steps(self, fix_group):
        """Perform modifications to the .opi file before doing the main conversion
        to .bob using the Phoebus converter."""
        return pre_conversion_steps()

    def run_post_conversion_steps(self, no_modify):
        """
        - Replaces EXIT scripts with an ActionButton to Exit
        - Action Buttons to open displays are modified to open .bob extensions
        - Rules using legacy severity are replaced
        - Flag that actions are running on non-action buttons
        """
        return post_conversion_steps()


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
            "Replaced .OPI file extensions with .BOB for "
            "EmbeddedDisplay/LinkingContainers/Open Display actions"
        )
    if log_data.non_ab_action:
        logger.warning(
            "Found an action on a widget that is NOT an ActionButton or Symbol widget. "
            "Debug for more"
        )
    if log_data.replace_with_ab:
        logger.info(
            "Replaced a Rectangle/BooleanButton widget with an action with an Action "
            "Button widget"
        )
    if log_data.replace_db_script:
        logger.info(
            "Replaced script to open databrowser with an action to open a DataBrowser "
            "plt file"
        )
    if log_data.fix_action_macro_name:
        logger.info(
            "Fixed Open Display action that contains the $name macro that does not get "
            "parsed"
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

    # TODO: Here we create a ConversionConfig object and pass it to main

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


def convert_opi(
    conversion: ConversionConfig,
    fix_group=True,
    no_modify=False,
    replace_tab=False,
    no_edit_file=None,
) -> Path | None:

    tmp_file_path = conversion.dst_dir_path / "tmp.opi"

    sc = OpiConverter(
        conversion.src_file_path,
        conversion.dst_filename,
        conversion.dst_dir_path,
        tmp_file_path,
        conversion.template_file_path,
        replace_tab,
    )

    # Check the no_edit file to see if we should even run the conversion
    # Instead of doing it like this, we could read a comment at the top of the bob file
    if no_edit_file is not None:
        with open(no_edit_file) as f:
            lines = f.readlines()
            for line in lines:
                if conversion.src_file_path == line.strip():
                    logging.warning(
                        "!!! OPI file to be converted is in the 'no_edit' list"
                        "suggesting that it has had manual changes that should not be"
                        "overwritten.\n"
                        "If this is incorrect then remove this file from the "
                        f"{no_edit_file}.\n"
                        "Skipping this conversion"
                    )
                    return None

    # If conversion has already been run, delete previous BOB conversion
    sc.delete_old_file()

    # Modify the OPI file before running conversion
    use_modified_opi = sc.run_pre_conversion_steps(fix_group)

    # Should we use the modified OPI files
    if not use_modified_opi:
        # Copy the src file to the tmp location overwriting any existing tmp.opi. This
        # is done as autoconverting directly from the src file sometimes fails due to
        # read permission issues
        shutil.copy(conversion.src_file_path, tmp_file_path)

    # Run Phoebus converter
    conversion_success = sc.run_converter(tmp_file_path)

    # Delete tmp.opi
    os.remove(tmp_file_path)

    if not conversion_success:
        return None

    # Rename tmp.bob to the required name
    new_file = os.path.join(conversion.dst_dir_path, conversion.dst_filename)
    tmp_file_path.with_suffix(".bob").rename(new_file)

    # Make modifications to converted .bob file
    sc.run_post_conversion_steps(no_modify)

    log_data = sc.cs
    log_conversion_steps(log_data)

    # Conversion failed, skip to next file
    if converted_file is None:
        continue

    # We need to define macros which were previously passed into the synoptic as
    # script arguments
    if conversion.synoptic:
        self.handle_macros(converted_file, conversion)

    # Figure out which filepaths within bob files need updating and
    # update them to the new paths.
    self.get_required_support_modules(conversion, converted_file)
    # Support module paths are relative and so don't need to have their paths
    # updated
    if conversion.support_module_name is None:
        self.update_filepaths(conversion)

    # Special cases are tweaks which are not handled by the
    # normal conversion process and are often unique to a specific screen.
    # These are optionally defined in a domain-specific special case module.
    try:
        self.special_case_module.run(converted_file, conversion)
    except AttributeError:
        pass

    # Overwrite the bob file with the modified xml data
    conversion.write_bob_file_contents()

    logger.info(f"Conversion saved to {converted_file}\n")
    return Path(new_file)


if __name__ == "__main__":
    convert_opi(*parse_args())
