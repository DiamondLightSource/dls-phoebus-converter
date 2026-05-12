"""Handles the conversion of an individual file from opi to bob"""

import argparse
import copy
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from dls_phoebus_converter.logconfig import setup_logging
from dls_phoebus_converter.post_converter import post_conversion_steps
from dls_phoebus_converter.pre_converter import pre_conversion_steps

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


@dataclass
class OpiConverter:
    src_file_path: Path
    dst_dir_path: Path
    dst_filename: str | None = None
    output_file: Path | None = None
    tmp_file_path: Path | None = None
    template_file_path: Path | None = None
    support_module_name: str | None = None
    no_edit_file: Path | None = None
    macros: dict[str, str] = field(default_factory=lambda: {})
    conversion_steps = ConversionSteps()

    synoptic: bool = False
    replace_tab: bool = True
    fix_group: bool = True
    no_modify: bool = False

    # This stores template file data
    template_data: etree.ElementTree | None = None

    # This stores the initial contents of the bob/opi file
    const_bob_data: etree.ElementTree | None = None
    const_opi_data: etree.ElementTree | None = None

    # This stores the working etree for the bob/opi data
    bob_data: etree.ElementTree | None = None
    opi_data: etree.ElementTree | None = None

    def __post_init__(self):
        if self.dst_filename is None:
            self.dst_filename = self.src_file_path.name.replace(".opi", ".bob")
        if self.output_file is None:
            self.output_file = self.dst_dir_path / self.dst_filename
        if self.tmp_file_path is None:
            self.tmp_file_path = self.dst_dir_path / "tmp.opi"

        self.read_template_file_contents()
        self.read_opi_file_contents()
        # If conversion has already been run, delete previous BOB conversion
        self.delete_old_file()

    def read_template_file_contents(self):
        if self.template_file_path is not None:
            self.template_data = etree.parse(self.template_file_path)

    def read_opi_file_contents(self):
        self.opi_data = etree.parse(self.src_file_path)
        self.const_opi_data = copy.deepcopy(self.opi_data)

    def read_bob_file_contents(self, output_file=None):
        if output_file is None:
            output_file = self.output_file
        self.bob_data = etree.parse(output_file)
        self.const_bob_data = copy.deepcopy(self.bob_data)

    def write_opi_file_contents(self):
        self.opi_data.write(self.tmp_file_path)

    def write_bob_file_contents(self):

        etree.indent(self.bob_data, space="    ")
        for el in self.bob_data.iter():
            if el.attrib.items() and not list(el):
                if el.text is not None and "\n" in el.text:
                    el.text = el.text.strip("\n")
                    el.text = el.text.strip()
            elif el.tag == "actions" and el.text is not None:
                el.text = el.text.strip("\n")
                el.text = el.text.strip()

        self.bob_data.write(
            self.output_file,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        )

    def delete_old_file(self):
        try:
            old_file = self.output_file
            os.remove(old_file)
            logger.info(f"Removing old converted file: {old_file}")
        except OSError:
            pass

    def dont_edit_file(self):
        # Check the no_edit file to see if we should even run the conversion
        # Instead of doing it like this, we could read a comment at the top of the bob file
        if self.no_edit_file is not None:
            with open(self.no_edit_file) as f:
                lines = f.readlines()
                for line in lines:
                    if self.src_file_path == line.strip():
                        logging.warning(
                            "!!! OPI file to be converted is in the 'no_edit' list"
                            "suggesting that it has had manual changes that should not be"
                            "overwritten.\n"
                            "If this is incorrect then remove this file from the "
                            f"{self.no_edit_file}.\n"
                            "Skipping this conversion"
                        )
                        return True
        return False

    def log_conversion_steps(self):
        # Log what was done
        if self.conversion_steps.replace_edm_sym:
            logger.info("Replaced EDMSymbol widgets in OPI before running converter")
        if self.conversion_steps.fix_group_cont:
            logger.info(
                "Fixed Grouping Container widget is OPI that is missing required properties"
            )
        if self.conversion_steps.update_leg_sev:
            logger.info("Updating legacy PV severity status")
        if self.conversion_steps.fix_exit_but:
            logger.info(
                "Converting EXIT to script to an EXIT action button to close display"
            )
        if self.conversion_steps.replace_opi_ext:
            logger.info(
                "Replaced .OPI file extensions with .BOB for "
                "EmbeddedDisplay/LinkingContainers/Open Display actions"
            )
        if self.conversion_steps.non_ab_action:
            logger.warning(
                "Found an action on a widget that is NOT an ActionButton or Symbol widget. "
                "Debug for more"
            )
        if self.conversion_steps.replace_with_ab:
            logger.info(
                "Replaced a Rectangle/BooleanButton widget with an action with an Action "
                "Button widget"
            )
        if self.conversion_steps.replace_db_script:
            logger.info(
                "Replaced script to open databrowser with an action to open a DataBrowser "
                "plt file"
            )
        if self.conversion_steps.fix_action_macro_name:
            logger.info(
                "Fixed Open Display action that contains the $name macro that does not get "
                "parsed"
            )
        if self.conversion_steps.create_sym_images:
            logger.info("Created new images for Symbol widget from original")
        if self.conversion_steps.replace_action_tab:
            logger.info("Replace open display target=tab with target=standalone")

    def run_converter(self):
        convert_command = (
            PHOEBUS_SH_FILE_PATH
            + "\
        -main org.csstudio.display.builder.model.Converter -output "
            + str(self.dst_dir_path)
            + " "
            + str(self.tmp_file_path)
        )
        process = subprocess.Popen(
            convert_command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        tmp_bob_file_path = self.dst_dir_path / "tmp.bob"

        # Captures the stdout and stderr from the converter process.
        # This can be very verbose, so we log it at the DEBUG level
        stdout, stderr = process.communicate()

        # Delete input file (tmp.opi)
        os.remove(self.tmp_file_path)

        if not tmp_bob_file_path.is_file():
            logger.error(f"Phoebus conversion command failed: {convert_command}")
        for line in stderr.decode("utf-8").split("\n"):
            if not tmp_bob_file_path.is_file():
                logger.error(line)
            logger.debug(line)

        if tmp_bob_file_path.is_file():
            # Read tmp.bob
            self.read_bob_file_contents(tmp_bob_file_path)
            # Delete tmp.bob
            os.remove(tmp_bob_file_path)
            return True
        else:
            return False

    def run_pre_conversion_steps(self):
        """Perform modifications to the .opi file before doing the main conversion
        to .bob using the Phoebus converter."""
        return pre_conversion_steps(self)

    def run_post_conversion_steps(self, sc):
        """Perform modifications to the .bob file.
        - Replaces EXIT scripts with an ActionButton to Exit
        - Action Buttons to open displays are modified to open .bob extensions
        - Rules using legacy severity are replaced
        - Flag that actions are running on non-action buttons
        - Change filepaths to reference new support module screen locations
        - Add macros as needed
        """
        return post_conversion_steps(self, sc)

    def convert(self, sc) -> Path | None:
        if self.dont_edit_file():
            return True

        # Modify the OPI file before running conversion
        use_modified_opi = self.run_pre_conversion_steps()

        # Should we use the modified OPI files
        if not use_modified_opi:
            # Copy the src file to the tmp location overwriting any existing tmp.opi. This
            # is done as autoconverting directly from the src file sometimes fails due to
            # read permission issues
            shutil.copy(self.src_file_path, self.tmp_file_path)

        # Run Phoebus converter
        success = self.run_converter()
        if not success:
            return False

        # Make modifications to converted .bob file
        self.run_post_conversion_steps(sc)

        # Write the final xml to the bob file
        self.write_bob_file_contents()

        self.log_conversion_steps()
        logger.info(f"Conversion saved to {self.output_file}\n")


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


if __name__ == "__main__":
    oc = OpiConverter(*parse_args())
    oc.convert()
