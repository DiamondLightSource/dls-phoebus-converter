"""Handles the entire conversion of a set of screens from a config.yaml file"""

import logging
from importlib import import_module
from pathlib import Path, PosixPath

import yaml

from dls_phoebus_converter.logconfig import setup_logging
from dls_phoebus_converter.opi_converter import OpiConverter
from dls_phoebus_converter.support_modules import convert_extra_support_modules

setup_logging()
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
        self.acc_ui_support_dst_full.mkdir(parents=True, exist_ok=True)
        self.domain_synoptic_dst_full.mkdir(parents=True, exist_ok=True)
        self.domain_ui_support_dst_full.mkdir(parents=True, exist_ok=True)

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

        self.domain_synoptic_dst_part = Path(meta_data["domain_synoptic_dst"])
        self.acc_ui_support_dst_part = Path(meta_data["acc_ui_support_dst"])
        self.domain_ui_support_dst_part = Path(meta_data["domain_ui_support_dst"])

        self.domain_synoptic_dst_full = (
            self.output_dir_path / meta_data["domain_synoptic_dst"]
        )
        self.acc_ui_support_dst_full = (
            self.output_dir_path
            / meta_data["domain_synoptic_dst"]
            / meta_data["acc_ui_support_dst"]
        )
        self.domain_ui_support_dst_full = (
            self.output_dir_path
            / meta_data["domain_synoptic_dst"]
            / meta_data["domain_ui_support_dst"]
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
        support_module_name = None

        if "support_module_name" in file_data:
            support_module_name = file_data["support_module_name"]

        # Common support module area shared across Accelerator Controls
        if file_data["dst"] == "acc-ui-support":
            dst_path_config = self.acc_ui_support_dst_full
            dst_path_partial = self.acc_ui_support_dst_part
        # Domain specific screens
        elif file_data["dst"] == f"{self.domain}-ui-support":
            dst_path_config = self.domain_ui_support_dst_full
            dst_path_partial = self.domain_ui_support_dst_part
        # Top level screens
        elif file_data["dst"] == "synoptic":
            dst_path_config = self.domain_synoptic_dst_full
            dst_path_partial = self.domain_synoptic_dst_part
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

            if "include_subdirs" in file_data and file_data["include_subdirs"] is True:
                for file_paths in src_path_config.rglob("*.opi"):
                    src_file_paths.append(file_paths)

                    if support_module_name is not None:
                        recursive_dir = Path(support_module_name)
                    else:
                        recursive_dir = Path(src_path_config.name)

                    # We need to do some fancy path manipulation to recreate the old
                    # directory structure in the destination directory
                    if len(file_paths.parent.parts) > len(src_path_config.parts):
                        for subdir in file_paths.parent.parts[
                            len(src_path_config.parts) :
                        ]:
                            recursive_dir = recursive_dir / subdir

                        qualified_module_name = "-".join(recursive_dir.parts)
                        if (
                            qualified_module_name,
                            dst_path_partial / recursive_dir,
                        ) not in self.domain_support_module_locations:
                            self.domain_support_module_locations.append(
                                (
                                    qualified_module_name,
                                    dst_path_partial / recursive_dir,
                                )
                            )

                    new_dst = dst_path_config / recursive_dir
                    dst_dir_paths.append(new_dst)
            else:
                for file_paths in src_path_config.glob("*.opi"):
                    if file_paths not in processed_files:
                        src_file_paths.append(file_paths)
                        dst_dir_paths.append(dst_path_config)
                    else:
                        logger.warning(
                            f"File {file_paths} has already been processed, skipping "
                            "conversion."
                        )
        else:
            src_file_paths = [src_path_config]
            dst_dir_paths = [dst_path_config]

        for src_file_path, dst_dir_path in zip(
            src_file_paths, dst_dir_paths, strict=True
        ):
            dst_filename = None
            template_file_path = None
            macros = None
            synoptic = None

            if "new_filename" in file_data:
                dst_filename = file_data["new_filename"]

            if "macros" in file_data:
                macros = file_data["macros"]

            if "support_module_name" in file_data:
                support_module_name = support_module_name
            else:
                support_module_name = None

            if "template_file" in file_data:
                template_file_path = Path(file_data["template_file"])
                if template_file_path.is_file():
                    template_file_path = template_file_path
                else:
                    template_file_path = (
                        Path.cwd() / "config/templates" / template_file_path
                    )

            if file_data["dst"] == "synoptic":
                synoptic = True

            new_conversion = OpiConverter(
                src_file_path=src_file_path,
                dst_dir_path=dst_dir_path,
                dst_filename=dst_filename,
                template_file_path=template_file_path,
                support_module_name=support_module_name,
                synoptic=synoptic,
                macros=macros,
            )

            new_conversions.append(new_conversion)

        return new_conversions

    def convert(self) -> None:
        for conversion in self.conversion_data:
            logger.info(f"Converting {conversion.src_file_path}")

            # Create directories to place screens
            conversion.dst_dir_path.mkdir(parents=True, exist_ok=True)

            # Convert .opi to .bob
            conversion.convert(self)

        # Get missing support module screens
        if self.convert_dependencies:
            convert_extra_support_modules(self)
