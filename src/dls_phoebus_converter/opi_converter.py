"""Handles the conversion of an individual file from opi to bob"""

import copy
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from dls_phoebus_converter.phoebus_runner import run_phoebus_converter
from dls_phoebus_converter.post_converter import post_conversion_steps
from dls_phoebus_converter.pre_converter import pre_conversion_steps

logger = logging.getLogger("dls_phoebus_converter")


def convert_single_screen(src_file_path: Path, output_dir_path: Path) -> bool:
    """Convert one screen, without a config file.

    Args:
        src_file_path: The .opi file to convert.
        output_dir_path: Directory to write the screen and its symbols to.

    Returns:
        True if the screen was converted and saved.
    """

    converter = OpiConverter(src_file_path, output_dir_path, output_dir_path)
    logger.info(f"Converting {src_file_path}")

    converter.dst_bob_dir_path.mkdir(parents=True, exist_ok=True)
    converter.dst_symbols_dir_path.mkdir(parents=True, exist_ok=True)

    return converter.convert()


@dataclass
class CompletedSteps:
    """Steps are marked as done if completed successfully, used for logging"""

    replace_edm_sym: bool = False
    fix_group_cont: bool = False
    update_leg_sev: bool = False
    fix_exit_but: bool = False
    replace_opi_ext: bool = False
    non_ab_action: bool = False
    replace_with_ab: bool = False
    replace_db_script: bool = False
    fix_action_macro_name: bool = False
    split_sym_images: bool = False
    replace_action_tab: bool = False


@dataclass
class OpiConverter:
    src_file_path: Path
    dst_bob_dir_path: Path
    dst_symbols_dir_path: Path
    path_to_top: Path = Path()
    dst_bob_filename: str | None = None
    dst_bob_filepath: Path | None = None
    staged_opi_path: Path | None = None

    support_module_name: str | None = None
    macros: dict[str, str] = field(default_factory=dict)
    completed_conversion_steps: CompletedSteps = field(default_factory=CompletedSteps)

    # This stores template file data
    template_data: etree.ElementTree | None = None

    # This stores the initial contents of the bob/opi file
    const_opi_data: etree.ElementTree | None = None
    const_bob_data: etree.ElementTree | None = None

    # This stores the working etree for the bob/opi data
    opi_data: etree.ElementTree | None = None
    bob_data: etree.ElementTree | None = None

    def __post_init__(self):
        if self.dst_bob_filename is None:
            self.dst_bob_filename = self.src_file_path.with_suffix(".bob").name
        if self.dst_bob_filepath is None:
            self.dst_bob_filepath = self.dst_bob_dir_path / self.dst_bob_filename

        self.read_opi_file_contents()
        # If conversion has already been run, delete previous BOB conversion
        self.delete_old_file()

    def read_opi_file_contents(self):
        self.opi_data = etree.parse(self.src_file_path)
        self.const_opi_data = copy.deepcopy(self.opi_data)

    def delete_old_file(self):
        try:
            old_file = self.dst_bob_filepath
            os.remove(old_file)
            logger.info(f"Removing old converted file: {old_file}")
        except OSError:
            pass

    def convert(self, sc=None) -> bool:
        """Convert this screen on its own, with its own Phoebus invocation.

        Args:
            sc: The conversion configuration, or None for a single file.

        Returns:
            True if the screen was converted and saved.
        """

        staging_dir = Path(tempfile.mkdtemp())
        try:
            staged_opi_path = staging_dir / "tmp.opi"
            self.stage_opi_file(staged_opi_path)

            failed_file_names = run_phoebus_converter([staged_opi_path], staging_dir)
            if staged_opi_path.name in failed_file_names:
                logger.error(
                    f"The Phoebus converter could not convert {self.src_file_path}, "
                    "so its screen will be empty"
                )

            return self.apply_conversion(staged_opi_path.with_suffix(".bob"), sc)
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    def stage_opi_file(self, staged_opi_path: Path) -> None:
        """Prepare the .opi that the Phoebus converter should read.

        Args:
            staged_opi_path: Where to put the prepared file. The Phoebus converter
                names its output after this, so it must be unique within a batch.
        """

        self.staged_opi_path = staged_opi_path

        # Modify the OPI file before running conversion. If modifications are made, file
        # is copied over to staged_opi_path by run_pre_conversion_steps()
        use_modified_opi = self.run_pre_conversion_steps()
        if not use_modified_opi:
            # Copy the src file to the staged location. This is done as autoconverting
            # directly from the src file sometimes fails due to read permission issues
            shutil.copy(self.src_file_path, self.staged_opi_path)

    def run_pre_conversion_steps(self):
        """Perform modifications to the .opi file before doing the main conversion
        to .bob using the Phoebus converter."""
        return pre_conversion_steps(self)

    def write_opi_file_contents(self):
        self.opi_data.write(self.staged_opi_path)

    def apply_conversion(self, staged_bob_path: Path, sc) -> bool:
        """Finish a conversion from what the Phoebus converter produced.

        Args:
            staged_bob_path: The .bob the Phoebus converter wrote for this screen.
            sc: The conversion configuration, or None for a single file.

        Returns:
            True if the screen was converted and saved.
        """

        os.remove(self.staged_opi_path)

        if not staged_bob_path.is_file():
            logger.error(f"Phoebus conversion failed for: {self.src_file_path}")
            return False

        self.read_bob_file_contents(staged_bob_path)
        os.remove(staged_bob_path)

        # Make modifications to converted .bob file
        self.run_post_conversion_steps(sc)

        # Write the final xml to the bob file
        self.write_bob_file_contents()

        self.log_conversion_steps()
        logger.info(f"Conversion saved to {self.dst_bob_filepath}\n")

        return True

    def read_bob_file_contents(self, output_file=None):
        if output_file is None:
            output_file = self.dst_bob_filepath
        self.bob_data = etree.parse(output_file)
        self.const_bob_data = copy.deepcopy(self.bob_data)

    def run_post_conversion_steps(self, sc):
        """Perform modifications to the .bob file.
        - Replaces EXIT scripts with an ActionButton to Exit
        - Action Buttons to open displays are modified to open .bob extensions
        - Rules using legacy severity are replaced
        - Flag that actions are running on non-action buttons
        - Change filepaths to reference new support module screen locations
        - Add macros as needed
        """
        return post_conversion_steps(sc, self)

    def write_bob_file_contents(self):

        etree.indent(self.bob_data, space="\t")

        # We must remove some dodgey formatting from certain elements inherited from the
        # opi file
        for el in self.bob_data.iter():
            if el.text is None:
                continue
            if (el.attrib and len(el) == 0) or el.tag in ("actions", "scripts"):
                el.text = el.text.strip()

        self.bob_data.write(
            self.dst_bob_filepath,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        )

    def log_conversion_steps(self):
        # Log what was done
        ccs = self.completed_conversion_steps
        conversion_steps = [
            (
                ccs.replace_edm_sym,
                "Replaced EDMSymbol widgets in OPI before running converter",
            ),
            (
                ccs.fix_group_cont,
                "Fixed Grouping Container widget in OPI that is missing "
                "required properties",
            ),
            (ccs.update_leg_sev, "Updating legacy PV severity status"),
            (
                ccs.fix_exit_but,
                "Converting EXIT to script to an EXIT action button to "
                "close the display",
            ),
            (
                ccs.replace_opi_ext,
                "Replaced .OPI file extensions with .BOB for "
                "EmbeddedDisplay/LinkingContainers/Open Display actions",
            ),
            (
                ccs.non_ab_action,
                "Found an action on a widget that is NOT an ActionButton"
                " or Symbol widget. Debug for more",
            ),
            (
                ccs.replace_with_ab,
                "Replaced a Rectangle/BooleanButton widget with an "
                "action, with an Action Button widget",
            ),
            (
                ccs.replace_db_script,
                "Replaced script to open databrowser with an action "
                "to open a DataBrowser plt file",
            ),
            (
                ccs.fix_action_macro_name,
                "Fixed Open Display action that contains the "
                "$name macro that does not get parsed",
            ),
            (
                ccs.split_sym_images,
                "Split the combined Symbol widget image into one image per symbol",
            ),
            (
                ccs.replace_action_tab,
                "Replace open display target=tab with target=standalone",
            ),
        ]
        for conversion_step_complete, conversion_step_log_msg in conversion_steps:
            if conversion_step_complete:
                logger.info(conversion_step_log_msg)
