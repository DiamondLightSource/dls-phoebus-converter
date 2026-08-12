"""Handles the entire conversion of a set of screens from a config.yaml file"""

import logging
from importlib import import_module
from pathlib import Path, PosixPath

import yaml

from dls_phoebus_converter.opi_converter import OpiConverter
from dls_phoebus_converter.support_modules import convert_extra_support_modules

logger = logging.getLogger("dls_phoebus_converter")


class ScreenConverter:
    def __init__(
        self, config_file_path: Path, output_dir_path: Path, debug: bool = False
    ) -> None:
        self.debug = debug
        self.output_dir_path = output_dir_path
        self.config_file = config_file_path
        self.convert_dependencies = False
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

    def get_config(self, config_file: Path | str) -> None:
        # get useful data out of json
        if type(config_file) is PosixPath:
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
        if "convert_dependencies" in meta_data:
            self.convert_dependencies = bool(meta_data["convert_dependencies"])

    def parse_file_data(
        self, file_data: dict, processed_files: list
    ) -> list[OpiConverter]:
        new_conversions = []
        src_file_paths = []
        dst_dir_paths = []
        src_path_config = Path(file_data["src"])
        dst_path_config = Path()
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
                    if (
                        "include_subdirs" in file_data
                        and file_data["include_subdirs"] is True
                    ):
                        src_file_paths.append(file_paths)
                        recursive_dir = Path()

                        # We need to do some fancy path manipulation to recreate the old
                        # directory structure in the destination directory
                        if len(file_paths.parent.parts) > len(src_path_config.parts):
                            for subdir in file_paths.parent.parts[
                                len(src_path_config.parts) :
                            ]:
                                recursive_dir = recursive_dir / subdir

                            qualified_module_name = support_module_name
                            if (
                                qualified_module_name,
                                dst_path_partial,
                            ) not in self.domain_support_module_locations:
                                self.domain_support_module_locations.append(
                                    (
                                        qualified_module_name,
                                        dst_path_partial,
                                    )
                                )

                        new_dst = dst_path_config / recursive_dir
                        dst_dir_paths.append(new_dst)
                    else:
                        if file_paths not in processed_files:
                            src_file_paths.append(file_paths)
                            dst_dir_paths.append(dst_path_config)
                else:
                    logger.warning(
                        f"File {file_paths} has already been processed, will not make "
                        "new conversion configuration."
                    )
        else:
            src_file_paths = [src_path_config]
            dst_dir_paths = [dst_path_config]

        for src_opi_file_path, dst_bob_dir_path in zip(
            src_file_paths, dst_dir_paths, strict=True
        ):
            dst_bob_filename = None
            macros = None

            if "new_filename" in file_data:
                dst_bob_filename = file_data["new_filename"]

            if "macros" in file_data:
                macros = file_data["macros"]

            file_depth = len(dst_bob_dir_path.parts) - len(self.output_dir_path.parts)
            path_to_top = path_to_top = Path(*["../"] * file_depth)
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
        for conversion in self.conversion_data:
            logger.info(f"Converting {conversion.src_file_path}")

            # Create directories to place screens
            conversion.dst_bob_dir_path.mkdir(parents=True, exist_ok=True)
            # Create directory to place symbols
            conversion.dst_symbols_dir_path.mkdir(parents=True, exist_ok=True)

            # Convert .opi to .bob
            conversion.convert(self)

        # Get missing support module screens
        if self.convert_dependencies:
            convert_extra_support_modules(self)
