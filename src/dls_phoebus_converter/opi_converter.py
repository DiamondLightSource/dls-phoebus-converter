"""Handles the conversion of an individual file from opi to bob"""

import copy
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from dls_phoebus_converter.post_converter import post_conversion_steps
from dls_phoebus_converter.pre_converter import pre_conversion_steps

PHOEBUS_SH_FILE_PATH = "/dls_sw/deploy-tools/modules/phoebus/dev/entrypoints/phoebus"
PLOT_LOCATION_MACRO = "$(PLOT_LOC)"

logger = logging.getLogger("dls_phoebus_converter")

# Screens are converted in batches to avoid container/phoebus overhead. Capped so that a
# long run reports progress as it goes, rather than going quiet for minutes at a time.
PHOEBUS_BATCH_SIZE = 100


def run_phoebus_converter(
    opi_file_paths: list[Path], output_dir_path: Path
) -> set[str]:
    """Convert .opi files to .bob with the Phoebus converter.

    Each output is named after its input, so the inputs must have distinct names.

    Args:
        opi_file_paths: The .opi files to convert.
        output_dir_path: Directory the converter writes the .bob files to.

    Returns:
        The filenames the converter reported it could not convert. It still writes an
        empty .bob for these, so they cannot be found by looking for a missing file.
    """

    failed_file_names: set[str] = set()

    for start in range(0, len(opi_file_paths), PHOEBUS_BATCH_SIZE):
        batch = opi_file_paths[start : start + PHOEBUS_BATCH_SIZE]
        convert_command = [
            *PHOEBUS_SH_FILE_PATH.split(),
            "-main",
            "org.csstudio.display.builder.model.Converter",
            "-output",
            str(output_dir_path),
            *[str(path) for path in batch],
        ]
        logger.info(f"Running the Phoebus converter on {len(batch)} screens")

        process = subprocess.Popen(
            convert_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        _, stderr = process.communicate()
        stderr_text = stderr.decode("utf-8")

        # The converter is very verbose, so it is logged at the DEBUG level
        for line in stderr_text.split("\n"):
            if line != "":
                logger.debug(f"Phoebus - {line}")

        failed_file_names.update(
            Path(reported).name
            for reported in re.findall(r"Cannot convert (\S+)", stderr_text)
        )

    return failed_file_names


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
    conversions_to_skip_filepath: Path | None = None

    support_module_name: str | None = None
    macros: dict[str, str] = field(default_factory=lambda: {})
    completed_conversion_steps: CompletedSteps = field(default_factory=CompletedSteps)

    replace_tab: bool = True
    fix_group: bool = True

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
        if self.staged_opi_path is None:
            self.staged_opi_path = self.dst_bob_dir_path / "tmp.opi"

        self.read_opi_file_contents()
        # If conversion has already been run, delete previous BOB conversion
        self.delete_old_file()

    def read_opi_file_contents(self):
        self.opi_data = etree.parse(self.src_file_path)
        self.const_opi_data = copy.deepcopy(self.opi_data)

    def read_bob_file_contents(self, output_file=None):
        if output_file is None:
            output_file = self.dst_bob_filepath
        self.bob_data = etree.parse(output_file)
        self.const_bob_data = copy.deepcopy(self.bob_data)

    def write_opi_file_contents(self):
        self.opi_data.write(self.staged_opi_path)

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
            self.dst_bob_filepath,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        )

    def delete_old_file(self):
        try:
            old_file = self.dst_bob_filepath
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
                        logger.warning(
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

    def stage_opi_file(self, staged_opi_path: Path) -> bool:
        """Prepare the .opi that the Phoebus converter should read.

        Args:
            staged_opi_path: Where to put the prepared file. The Phoebus converter
                names its output after this, so it must be unique within a batch.

        Returns:
            True if the file was staged and should be converted.
        """

        if self.is_conversion_allowed():
            return False

        self.staged_opi_path = staged_opi_path

        # Modify the OPI file before running conversion
        use_modified_opi = self.run_pre_conversion_steps()
        if not use_modified_opi:
            # Copy the src file to the staged location. This is done as autoconverting
            # directly from the src file sometimes fails due to read permission issues
            shutil.copy(self.src_file_path, self.staged_opi_path)

        return True

    def apply_conversion(self, staged_bob_path: Path, sc) -> bool:
        """Finish a conversion from what the Phoebus converter produced.

        Args:
            staged_bob_path: The .bob the Phoebus converter wrote for this screen.
            sc: The running conversion, or None for a single file.

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
        """Convert this screen on its own, with its own Phoebus invocation."""

        staging_dir = Path(tempfile.mkdtemp())
        try:
            staged_opi_path = staging_dir / "tmp.opi"
            if not self.stage_opi_file(staged_opi_path):
                return True

            failed_file_names = run_phoebus_converter([staged_opi_path], staging_dir)
            if staged_opi_path.name in failed_file_names:
                logger.error(
                    f"The Phoebus converter could not convert {self.src_file_path}, "
                    "so its screen will be empty"
                )

            if not self.apply_conversion(staged_opi_path.with_suffix(".bob"), sc):
                return False
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
