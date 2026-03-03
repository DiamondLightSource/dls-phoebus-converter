from argparse import ArgumentParser
import re

import opi_converter
import yaml
import logging
from pathlib import Path
import xmltodict
from dataclasses import dataclass, field
from logconfig import setup_logging

MACRO_EXCEPTION_LIST = ["pv_name", "pv_value", "name", "actions"]

setup_logging()
logger = logging.getLogger("dls_phoebus_converter")


@dataclass
class ConversionConfig:
    src_path: Path = Path()
    dst_dir: Path = Path()
    dst_file: str = None
    synoptic: bool = False
    macros: dict[str, str] = field(default_factory=lambda: {})


class Converter:
    def __init__(self,
                 config_file: Path,
                 output_dir: Path,
                 debug: bool = False) -> None:
        self.debug = debug
        self.output_dir = output_dir
        # Mapping between a screens src path and destination dir
        self.conversion_data: list[ConversionConfig] = []
        # Mapping between a support module name and its screen location dir
        self.support_module_locations: list[tuple] = []
        self.get_config(config_file)

    def get_config(self, config_file: Path) -> None:
        # get useful data out of json
        with open(config_file, "r") as file:
            data = yaml.safe_load(file)
            self.parse_meta_data(data["meta_data"][0])
            all_file_data = data["files"]
            for file_data in all_file_data:
                self.conversion_data.extend(self.parse_file_data(file_data))

    def parse_meta_data(self, meta_data: dict) -> None:
        self.domain = meta_data["domain"]
        logger.info(f"Getting config data for domain: {self.domain}\n")

        self.acc_ui_support_dst_part = Path(meta_data["acc_ui_support_dst"])
        self.domain_synoptic_dst_part = Path(meta_data["domain_synoptic_dst"])
        self.domain_ui_support_dst_part = Path(meta_data["domain_ui_support_dst"])

        self.acc_ui_support_dst_full = self.output_dir / meta_data["acc_ui_support_dst"]
        self.domain_synoptic_dst_full = (
            self.output_dir / meta_data["domain_synoptic_dst"]
        )
        self.domain_ui_support_dst_full = (
            self.output_dir / meta_data["domain_ui_support_dst"]
        )

    def parse_file_data(self, file_data: dict) -> list[ConversionConfig]:
        new_conversions = []

        src_files = []
        dst_paths = []
        src_path_config = Path(file_data["src"])
        dst_path_config = Path()

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
                message = "The 'new_filename' field cannot be used when src is given as a directory. Please check config file."
                logger.error(message)
                raise ValueError(message)

            if "include_subdirs" in file_data and file_data["include_subdirs"] is True:
                for file in src_path_config.rglob("*.opi"):
                    src_files.append(file)
                    recursive_dir = Path("")

                    # We need to do some fancy path manipulation to recreate the old directory
                    # structure in the destination directory
                    if len(file.parent.parts) > len(src_path_config.parts):
                        for subdir in file.parent.parts[len(src_path_config.parts) :]:
                            recursive_dir = recursive_dir / subdir
                    if (
                        recursive_dir.parts[0],
                        dst_path_partial / recursive_dir,
                    ) not in self.support_module_locations:
                        self.support_module_locations.append(
                            (recursive_dir.parts[0], dst_path_partial / recursive_dir)
                        )

                    new_dst = dst_path_config / recursive_dir
                    dst_paths.append(new_dst)
            else:
                for file in src_path_config.glob("*.opi"):
                    src_files.append(file)
                    dst_paths.append(dst_path_config)
        else:
            src_files = [src_path_config]
            dst_paths = [dst_path_config]

        for src_file, dst_path in zip(src_files, dst_paths, strict=True):
            new_conversion = ConversionConfig()
            new_conversion.src_path = src_file
            new_conversion.dst_dir = dst_path
            if "new_filename" in file_data:
                new_conversion.dst_file = file_data["new_filename"]
            if "macros" in file_data:
                new_conversion.macros = file_data["macros"]
            if file_data["dst"] == "synoptic":
                new_conversion.synoptic = True
            new_conversions.append(new_conversion)

        return new_conversions

    def get_widget_dicts(self, file: Path) -> list[dict]:
        with open(file, "r", encoding="utf-8") as fh:
            fxml = fh.read()
            as_dict = xmltodict.parse(fxml)
            widgets = as_dict["display"]["widget"]
            return widgets

    def update_filepaths(self, file: Path) -> None:
        widgets = self.get_widget_dicts(file)
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            if "file" in widget:
                old_file_path = Path(widget["file"])
                if len(old_file_path.parts) == 1:
                    # No need to update filepath as looking for file in same dir
                    pass
                else:
                    support_module_found = False
                    for mapping in self.support_module_locations:
                        support_module = mapping[0]
                        if support_module in old_file_path.parts:
                            if support_module_found:
                                raise IndexError("Support module already found, issue?")
                            support_module_found = True
                            widget["file"] = mapping[1]
                            logger.info(
                                "Updated filepath for widget: "
                                + str({widget["name"]})
                                + f" to {mapping[1]}"
                            )
                    if not support_module_found:
                        logger.warning(
                            f"Could not find support module for file: {old_file_path}"
                        )
                        # raise IndexError(f"Could not find support module for file: {old_file_path}")

    def convert_generic_support_module(self):
        # Using only the name of the support module, attempt to find its bob files,
        # convert them to Phoebus and then save them in acc-ui-support/bob
        pass

    def add_new_macros(self, file: Path, macro_names: list[str], macro_values: list[str]):
        """Add a list of macro name/values to the top level of the bob file."""

        with open(file, "r", encoding="utf-8") as fh:
            fxml = fh.read()
            as_dict = xmltodict.parse(fxml)

        if "macros" not in as_dict["display"]:
            as_dict["display"]["macros"] = {}

        macro_data = as_dict["display"]["macros"]

        for new_macro_name, new_macro_value in zip(macro_names, macro_values, strict=True):
            for existing_macro_name, existing_macro_value in macro_data.items():
                if existing_macro_name == new_macro_name:
                    logging.warning(f"An existing file macro is being overwritten: "
                                    f"{existing_macro_name}:{existing_macro_value} -> "
                                    f"{new_macro_name}:{new_macro_value}") 
            macro_data[new_macro_name] = new_macro_value


        with open(file, "w") as fh:
            new_xml = xmltodict.unparse(as_dict, pretty=True)
            fh.write(new_xml)

    def handle_macros(self, file: Path, conversion: ConversionConfig) -> None:
        """Look for unique instances of a macro eg ${string} in the bob file. We ignore a small
        number of macros which are defined from other widget fields (MACRO_EXCEPTION_LIST).
        If a macro is found in a file but has not been defined in the ConversionConfig, then
        we log a warning."""

        new_macro_names=[]
        new_macro_values=[]

        with file.open("r", encoding="utf-8") as fh:
            content = fh.read()

        unique_identified_macros = set(re.findall(r"\$[\{\(]([^\}\)\s]+)[\}\)]", content))
        logger.info(f"Found macros in file: {unique_identified_macros}")

        for macro in unique_identified_macros:
            # Some macros refer to internal Phoebus objects, so we dont resolve these
            if macro not in MACRO_EXCEPTION_LIST:
                if macro in conversion.macros.keys():
                    new_macro_names.append(macro)
                    new_macro_values.append(conversion.macros[macro])
                else:
                    # This macro has not been defined!
                    logger.warning(f"Could not find definition for macro: '{macro}'. "
                                   "Should this have been defined in your yaml config?")
                    
        self.add_new_macros(file, new_macro_names, new_macro_values)

    def convert(self) -> None:
        for conversion in self.conversion_data:
            logger.info(f"Converting {conversion.src_path}")
            # Create directories to place screens, this should probably be in opi_converter.py
            conversion.dst_dir.mkdir(parents=True, exist_ok=True)
            # Convert .boy to .bob
            converted_file = opi_converter.main(
                conversion.src_path, conversion.dst_dir, conversion.dst_file
            )
            # We need to define macros which were previously passed into the synoptic as script arguments
            if conversion.synoptic:
                self.handle_macros(converted_file, conversion)
            # Update filepath within bob files to the new locations of screens
            self.update_filepaths(converted_file)
            logger.info(f"Conversion saved to {converted_file}\n")


def parse_arguments():
    """Parse command line arguments sent to virtac"""
    parser = ArgumentParser()
    parser.add_argument(
        "config_file",
        type=str,
        help="The yaml config for the conversion. This can either be a full path to a" \
        " .yaml file or the name of one of the .yaml files in config/",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        required=False,
        type=str,
        help="The full path to the directory to output generated files to",
        default=Path.cwd() / "output"
    )
    parser.add_argument(
        "-d",
        "--debug",
        help="Enable debug logging",
        action="store_true",
        default=False,
    )
    args = parser.parse_args()

    config_file = Path(args.config_file)
    # If the user only supplied the name of a config file, then add the path to the
    # directort containing the config files
    if len(config_file.parts) == 1:
        config_file = Path.cwd() / "config" / config_file
    
    if args.debug:
        logger.setLevel(logging.DEBUG)

    return config_file, Path(args.output_dir)

def main():
    args = parse_arguments()
    logger.debug(f"Running screen conversion with arguments: {args}")
    converter = Converter(config_file=args[0], output_dir=args[1])
    converter.convert()


if __name__ == "__main__":
    main()
