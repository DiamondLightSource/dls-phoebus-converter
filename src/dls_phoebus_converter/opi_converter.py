"""Handles the conversion of an individual file from opi to bob"""

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
class CompletedSteps:
    """Steps are marked as done if completed successfully, used for logging"""

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
    dst_filepath: Path | None = None
    tmp_file_path: Path | None = None
    template_file_path: Path | None = None
    conversions_to_skip_filepath: Path | None = None

    support_module_name: str | None = None
    macros: dict[str, str] = field(default_factory=lambda: {})
    completed_conversion_steps = CompletedSteps()

    synoptic: bool = False
    replace_tab: bool = True
    fix_group: bool = True
    no_modify: bool = False

    # This stores template file data
    template_data: etree.ElementTree | None = None

    # This stores the initial contents of the bob/opi file
    const_opi_data: etree.ElementTree | None = None
    const_bob_data: etree.ElementTree | None = None

    # This stores the working etree for the bob/opi data
    opi_data: etree.ElementTree | None = None
    bob_data: etree.ElementTree | None = None

    def __post_init__(self):
        if self.dst_filename is None:
            self.dst_filename = self.src_file_path.with_suffix(".bob").name
        if self.dst_filepath is None:
            self.dst_filepath = self.dst_dir_path / self.dst_filename
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
            output_file = self.dst_filepath
        self.bob_data = etree.parse(output_file)
        self.const_bob_data = copy.deepcopy(self.bob_data)

    def write_opi_file_contents(self):
        self.opi_data.write(self.tmp_file_path)

    def write_bob_file_contents(self):

        etree.indent(self.bob_data, space="\t")

        # We must remove some dodgey formatting from certain elements inherited from the
        # opi file
        for el in self.bob_data.iter():
            if el.attrib.items() and not list(el):
                if el.text is not None and "\n" in el.text:
                    el.text = el.text.strip("\n")
                    el.text = el.text.strip()
            elif (el.tag == "actions" or el.tag == "scripts") and el.text is not None:
                el.text = el.text.strip("\n")
                el.text = el.text.strip()

        self.bob_data.write(
            self.dst_filepath,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        )

    def delete_old_file(self):
        try:
            old_file = self.dst_filepath
            os.remove(old_file)
            logger.info(f"Removing old converted file: {old_file}")
        except OSError:
            pass

    def is_conversion_allowed(self):
        """Check the conversions_to_skip file to see if we should run the conversion for
        this file. Is this even useful?"""

        if self.conversions_to_skip_filepath is not None:
            with open(self.conversions_to_skip_filepath) as f:
                lines = f.readlines()
                for line in lines:
                    if self.src_file_path == line.strip():
                        logging.warning(
                            "!OPI file to be converted is in the 'conversions_to_skip' "
                            "list suggesting that it has had manual changes that should"
                            " not be overwritten.\n"
                            "If this is incorrect then remove this file from the "
                            f"{self.conversions_to_skip_filepath}.\n"
                            "Skipping this conversion"
                        )
                        return True
        return False

    def log_conversion_steps(self):
        # Log what was done
        ccs = self.completed_conversion_steps
        conversion_step_log_map = {
            ccs.replace_edm_sym: "Replaced EDMSymbol widgets in OPI before running "
            "converter",
            ccs.fix_group_cont: "Fixed Grouping Container widget in OPI that is missing"
            "required properties",
            ccs.update_leg_sev: "Updating legacy PV severity status",
            ccs.fix_exit_but: "Converting EXIT to script to an EXIT action button to "
            "close the display",
            ccs.replace_opi_ext: "Replaced .OPI file extensions with .BOB for "
            "EmbeddedDisplay/LinkingContainers/Open Display actions",
            ccs.non_ab_action: "Found an action on a widget that is NOT an ActionButton"
            " or Symbol widget. Debug for more",
            ccs.replace_with_ab: "Replaced a Rectangle/BooleanButton widget with an "
            "action, with an Action Button widget",
            ccs.replace_db_script: "Replaced script to open databrowser with an action "
            "to open a DataBrowser plt file",
            ccs.fix_action_macro_name: "Fixed Open Display action that contains the "
            "$name macro that does not get parsed",
            ccs.create_sym_images: "Created new images for Symbol widget from original",
            ccs.replace_action_tab: "Replace open display target=tab with "
            "target=standalone",
        }
        for (
            conversion_step_complete,
            conversion_step_log_msg,
        ) in conversion_step_log_map.items():
            if conversion_step_complete:
                logger.info(conversion_step_log_msg)

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

    def convert(self, sc=None) -> Path | None:
        if self.is_conversion_allowed():
            return True

        # Modify the OPI file before running conversion
        use_modified_opi = self.run_pre_conversion_steps()

        # Should we use the modified OPI files
        if not use_modified_opi:
            # Copy the src file to the tmp location overwriting any existing tmp.opi.
            # This is done as autoconverting directly from the src file sometimes fails
            # due to read permission issues
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
        logger.info(f"Conversion saved to {self.dst_filepath}\n")
