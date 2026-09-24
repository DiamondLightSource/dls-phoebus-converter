"""Handles the entire conversion of a set of screens from a config.yaml file"""

import logging
import shutil
import tempfile
from importlib import import_module
from pathlib import Path

import yaml

from dls_phoebus_converter.opi_converter import OpiConverter, run_phoebus_converter
from dls_phoebus_converter.support_modules import (
    UnpinnedModuleAction,
    convert_extra_support_modules,
    report_support_module_problems,
)

logger = logging.getLogger("dls_phoebus_converter")


class ScreenConverter:
    def __init__(
        self, config_file_path: Path, output_dir_path: Path, debug: bool = False
    ) -> None:
        self.debug = debug
        self.output_dir_path = output_dir_path
        self.config_file = config_file_path
        self.convert_dependencies = False
        # Mapping between a support module name and the release to convert from
        self.dependency_versions: dict[str, str] = {}
        self.on_unpinned_module = UnpinnedModuleAction.LATEST
        # Support module problems, collected during the run and reported once at the end
        self.unpinned_modules_found: set[str] = set()
        self.modules_without_screens: set[str] = set()
        # Symbol image destination -> (symbol width, number of symbols), so each image
        # is only split once per run
        self.symbol_image_splits: dict[Path, tuple[int, int]] = {}
        # Mapping between a screens src path and destination dir
        self.conversion_data: list[OpiConverter] = []
        # Mapping between a support module name and its screen location dir
        self.domain_support_module_locations: list[tuple] = []
        self.acc_support_module_locations: list[tuple] = []
        self.get_config(config_file_path)
        self.make_top_dirs()

        try:
            self.special_case_module = import_module(
                f"dls_phoebus_converter.{self.domain}_special_case"
            )
        except ModuleNotFoundError:
            logger.info(
                f"Could not import module: "
                f"dls_phoebus_converter.{self.domain}_special_case."
            )

    def make_top_dirs(self) -> None:
        self.acc_ui_support_bob_dst_full.mkdir(parents=True, exist_ok=True)
        self.acc_ui_support_symbol_dst_full.mkdir(parents=True, exist_ok=True)
        self.domain_ui_support_bob_dst_full.mkdir(parents=True, exist_ok=True)
        self.domain_ui_support_symbol_dst_full.mkdir(parents=True, exist_ok=True)

    def get_config(self, config_file: Path | dict) -> None:
        """Read the config and build the list of screens to convert.

        Args:
            config_file: The .yaml file to read, or config data that has already been
                parsed.
        """

        if isinstance(config_file, Path):
            with open(config_file) as file:
                data = yaml.safe_load(file)
        else:
            data = config_file
        self.parse_meta_data(data["meta_data"][0])
        all_file_data = data["files"]

        dir_index_list = []
        # Move directories last in the list so that single files
        # can be processed in more detail where required.
        for file_data in all_file_data:
            if Path(file_data["src"]).is_dir():
                dir_index_list.append(all_file_data.index(file_data))

        for index in dir_index_list:
            all_file_data.append(all_file_data.pop(index))

        processed_files: list[Path] = []
        for file_data in all_file_data:
            self.conversion_data.extend(
                self.parse_file_data(file_data, processed_files)
            )
            if Path(file_data["src"]).is_file():
                processed_files.append(Path(file_data["src"]))

    def parse_meta_data(self, meta_data: dict) -> None:
        self.domain = meta_data["domain"]
        logger.info(f"Getting config data for domain: {self.domain}\n")

        self.acc_ui_support_bob_dst_part = Path(meta_data["acc_ui_support_dst"]) / "bob"
        self.domain_ui_support_bob_dst_part = (
            Path(meta_data["domain_ui_support_dst"]) / "bob"
        )
        self.acc_ui_support_symbol_dst_part = (
            Path(meta_data["acc_ui_support_dst"]) / "symbols"
        )
        self.domain_ui_support_symbol_dst_part = (
            Path(meta_data["domain_ui_support_dst"]) / "symbols"
        )

        self.acc_ui_support_bob_dst_full = (
            self.output_dir_path / meta_data["acc_ui_support_dst"] / "bob"
        )
        self.domain_ui_support_bob_dst_full = (
            self.output_dir_path / meta_data["domain_ui_support_dst"] / "bob"
        )
        self.acc_ui_support_symbol_dst_full = (
            self.output_dir_path / meta_data["acc_ui_support_dst"] / "symbols"
        )
        self.domain_ui_support_symbol_dst_full = (
            self.output_dir_path / meta_data["domain_ui_support_dst"] / "symbols"
        )
        self.convert_dependencies = bool(meta_data.get("convert_dependencies"))

        # An empty dependencies field parses as None rather than an empty mapping
        self.dependency_versions = meta_data.get("dependencies") or {}

        if "on_unpinned_module" in meta_data:
            unpinned_action = meta_data["on_unpinned_module"]
            try:
                self.on_unpinned_module = UnpinnedModuleAction(unpinned_action)
            except ValueError:
                error_msg = (
                    "Invalid on_unpinned_module field in config file: "
                    f"{unpinned_action}. Expected one of "
                    f"{[action.value for action in UnpinnedModuleAction]}."
                )
                logger.error(error_msg)
                raise ValueError(error_msg) from None

    def parse_file_data(
        self, file_data: dict, processed_files: list
    ) -> list[OpiConverter]:
        new_conversions = []
        src_file_paths = []
        dst_dir_paths = []
        src_path_config = Path(file_data["src"])
        support_module_name = file_data["support_module_name"]

        # Common support module area shared across Accelerator Controls
        if file_data["dst"] == "acc-ui-support":
            dst_path_config = self.acc_ui_support_bob_dst_full / support_module_name
            dst_path_partial = self.acc_ui_support_bob_dst_part / support_module_name
            dst_symbols_dir_path = (
                self.acc_ui_support_symbol_dst_full / support_module_name
            )
        # Domain specific screens
        elif file_data["dst"] == f"{self.domain}-ui-support":
            dst_path_config = self.domain_ui_support_bob_dst_full / support_module_name
            dst_path_partial = self.domain_ui_support_bob_dst_part / support_module_name
            dst_symbols_dir_path = (
                self.domain_ui_support_symbol_dst_full / support_module_name
            )
        else:
            error_msg = f"Invalid dst field in config file: {file_data['dst']}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg)

        # If the src path is a directory, we find all .opi files within it and add them
        # to the conversion list, otherwise we add the single file specified
        # in the config
        if src_path_config.is_dir():
            if "new_filename" in file_data:
                message = (
                    "The 'new_filename' field cannot be used when src is given as "
                    "a directory. Please check config file."
                )
                logger.error(message)
                raise ValueError(message)

            for file_paths in src_path_config.rglob("*.opi"):
                if file_paths not in processed_files:
                    if file_data.get("include_subdirs") is True:
                        # We need to do some fancy path manipulation to recreate the old
                        # directory structure in the destination directory
                        recursive_dir = Path()

                        if len(file_paths.parent.parts) > len(src_path_config.parts):
                            for subdir in file_paths.parent.parts[
                                len(src_path_config.parts) :
                            ]:
                                recursive_dir = recursive_dir / subdir

                            module_location = (support_module_name, dst_path_partial)
                            if (
                                module_location
                                not in self.domain_support_module_locations
                            ):
                                self.domain_support_module_locations.append(
                                    module_location
                                )

                        src_file_paths.append(file_paths)
                        dst_dir_paths.append(dst_path_config / recursive_dir)
                    else:
                        src_file_paths.append(file_paths)
                        dst_dir_paths.append(dst_path_config)
                else:
                    logger.warning(
                        f"File {file_paths} has already been processed, will not make "
                        "duplicate conversion configuration."
                    )
        else:
            src_file_paths = [src_path_config]
            dst_dir_paths = [dst_path_config]

        for src_opi_file_path, dst_bob_dir_path in zip(
            src_file_paths, dst_dir_paths, strict=True
        ):
            dst_bob_filename = file_data.get("new_filename")
            macros = file_data.get("macros")

            file_depth = len(dst_bob_dir_path.parts) - len(self.output_dir_path.parts)
            path_to_top = Path(*["../"] * file_depth)
            new_conversion = OpiConverter(
                src_file_path=src_opi_file_path,
                dst_bob_dir_path=dst_bob_dir_path,
                dst_symbols_dir_path=dst_symbols_dir_path,
                path_to_top=path_to_top,
                dst_bob_filename=dst_bob_filename,
                support_module_name=support_module_name,
                macros=macros,
            )

            new_conversions.append(new_conversion)

        return new_conversions

    def convert(self) -> None:
        """Convert everything in the config, plus the support modules it depends on."""

        self.convert_screens()
        report_support_module_problems(self)

    def convert_screens(self) -> None:
        """Convert the screens currently listed in conversion_data.

        convert_extra_support_modules calls back into this with the screens of the
        support modules it has found, so this runs once per round of dependencies.
        """

        staging_dir_path = Path(tempfile.mkdtemp())
        try:
            staged = []
            for index, conversion in enumerate(self.conversion_data):
                logger.info(f"Converting {conversion.src_file_path}")

                # Create directories to place screens
                conversion.dst_bob_dir_path.mkdir(parents=True, exist_ok=True)
                # Create directory to place symbols
                conversion.dst_symbols_dir_path.mkdir(parents=True, exist_ok=True)

                # The Phoebus converter names its output after its input, so every
                # screen in a batch needs a distinct staged filename
                staged_opi_path = staging_dir_path / f"{index:05}.opi"
                if conversion.stage_opi_file(staged_opi_path):
                    staged.append((conversion, staged_opi_path))

            failed_file_names = run_phoebus_converter(
                [path for _, path in staged], staging_dir_path
            )

            for conversion, staged_opi_path in staged:
                if staged_opi_path.name in failed_file_names:
                    logger.error(
                        "The Phoebus converter could not convert "
                        f"{conversion.src_file_path}, so its screen will be empty"
                    )
                conversion.apply_conversion(staged_opi_path.with_suffix(".bob"), self)
        finally:
            shutil.rmtree(staging_dir_path, ignore_errors=True)

        # Get missing support module screens
        if self.convert_dependencies:
            convert_extra_support_modules(self)
