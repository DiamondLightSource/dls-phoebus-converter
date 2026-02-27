import re

import screen_converter
import yaml
import logging
from pathlib import Path
import xmltodict
from dataclasses import dataclass, field
from logconfig import setup_logging

MACRO_EXCEPTION_LIST = ["pv_name", "pv_value"]

setup_logging()
logger = logging.getLogger("dls_phoebus_converter")


@dataclass
class ConversionConfig:
    src_path = Path()
    dst_path = Path()
    dst_dir = Path()
    synoptic = False
    macros: dict[str, str] = field(default_factory=lambda: {})


class Converter:
    def __init__(self, output_dir, config_file, test):
        self.test = test
        self.output_dir = output_dir
        # Mapping between a screens src path and destination dir
        self.conversion_data: list[ConversionConfig] = []
        # Mapping between a support module name and its screen location dir
        self.support_module_locations: list[tuple] = []
        self.get_config(config_file)

    def get_config(self, config_file):
        # get useful data out of json
        with open(config_file, "r") as file:
            data = yaml.safe_load(file)
            self.parse_meta_data(data["meta_data"][0])
            all_file_data = data["files"]
            for file_data in all_file_data:
                self.conversion_data.extend(self.parse_file_data(file_data))

    def parse_meta_data(self, meta_data):
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

    def parse_file_data(self, file_data):
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
            if "macros" in file_data:
                new_conversion.macros = file_data["macros"]
            if file_data["dst"] == "synoptic":
                new_conversion.synoptic = True
            new_conversions.append(new_conversion)

        return new_conversions

    def get_widget_dicts(self, file):
        with open(file, "r", encoding="utf-8") as file:
            fxml = file.read()
            as_dict = xmltodict.parse(fxml)
            widgets = as_dict["display"]["widget"]
            return widgets

    def update_filepaths(self, file):
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
                            logger.info("Updated filepath for widget: " + str({widget["name"]}) + f" to {mapping[1]}")
                    if not support_module_found:
                        logger.warning(
                            f"Could not find support module for file: {old_file_path}"
                        )
                        # raise IndexError(f"Could not find support module for file: {old_file_path}")

    def convert_generic_support_module(self):
        # Using only the name of the support module, attempt to find its bob files,
        # convert them to Phoebus and then save them in acc-ui-support/bob
        pass

    def define_macros(self, file, conversion):
        # look for any instances of eg ${string}
        # see if there is already a macro resolution for the string either for the widget or file
        # if not, check if this is an edge case string (eg pv_name) which doesnt need defining here
        # if not try and add it if the conversion specifies a macro
        # if the string is not defined in conversion.macros then raise an error
        p = Path(file)
        with p.open("r", encoding="utf-8") as fh:
            content = fh.read()
        macros = set(re.findall(r"\$[\{\(]([^\}\)]+)[\}\)]", content))

        logger.info(f"Found macros in file: {macros}")
        # This is where we add the macro to the file or to a widget in the file where it is needed
        # But we can only do this if the macro was passed in to the converter.
        # TODO: Rewrite!
        for macro in macros:
            if macro not in MACRO_EXCEPTION_LIST:
                if f"<{macro}>" not in content:
                    if macro in conversion.macros.keys():
                        content = re.sub(
                            r"\$[\{\(]([^\}\)]+)[\}\)]",
                            str(conversion.macros[macro]),
                            content,
                        )
                    else:
                        # This macro has not been defined!
                        logger.warning(f"Could not find definition for macro: {macro}")
                        # raise KeyError("Macro missing!")

        with p.open("w", encoding="utf-8") as fh:
            fh.write(content)

    def convert(self):
        for conversion in self.conversion_data:
            logger.info(f"Converting {conversion.src_path}")
            # Create directories to place screens, this should probably be in screen_converter.py
            conversion.dst_dir.mkdir(parents=True, exist_ok=True)
            # Convert .boy to .bob
            converted_file = screen_converter.main(
                conversion.src_path, conversion.dst_dir
            )
            # We need to define macros which were previously passed into the file
            self.define_macros(converted_file, conversion)
            # Update filepaths
            self.update_filepaths(converted_file)
            logger.info(f"Conversion saved to {converted_file}\n")


def main(
    output_dir=Path.cwd() / "output",
    config_file=Path.cwd() / "config" / "example.yaml",
    test=True,
):
    converter = Converter(output_dir, config_file, test)
    converter.convert()


if __name__ == "__main__":
    main()
