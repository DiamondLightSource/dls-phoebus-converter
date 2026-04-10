from argparse import ArgumentParser
import re
import typing

import opi_converter
import yaml
import logging
from pathlib import Path, PosixPath
import xmltodict
from dataclasses import dataclass, field
from logconfig import setup_logging

MACRO_EXCEPTION_LIST = ["pv_name", "pv_value", "name", "actions"]
ACC_UI_SUPPORT_MODULE_LIST = ["devIocStats", "digitelMpc", "mks937a", "mpsPermit", "rga", "TimingTemplates"]

setup_logging()
logger = logging.getLogger("dls_phoebus_converter")


@dataclass
class ConversionConfig:
    src_file_path: Path = Path()
    dst_dir_path: Path = Path()
    dst_filename: str | None = None
    template_file_path: Path | None = None
    support_module_name: str | None = None
    synoptic: bool = False
    macros: dict[str, str] = field(default_factory=lambda: {})
    # This stores the entire contents of the bob file
    all_phoebus_data: dict = field(default_factory=lambda: {})
    # This just stores the widget data from the bob file
    widget_data: dict = field(default_factory=lambda: {})



class Converter:
    def __init__(
        self, config_file_path: Path, output_dir_path: Path, debug: bool = False
    ) -> None:
        self.debug = debug
        self.output_dir_path = output_dir_path
        self.config_file = config_file_path
        self.convert_dependencies = False
        # Mapping between a screens src path and destination dir
        self.conversion_data: list[ConversionConfig] = []
        # Mapping between a support module name and its screen location dir
        self.domain_support_module_locations: list[tuple] = []
        self.acc_support_module_locations: list[tuple] = []
        self.get_config(config_file_path)
        self.make_top_dirs()

    def make_top_dirs(self) -> None:
        self.acc_ui_support_dst_full.mkdir(parents=True, exist_ok=True)
        self.domain_synoptic_dst_full.mkdir(parents=True, exist_ok=True)
        self.domain_ui_support_dst_full.mkdir(parents=True, exist_ok=True)

    def get_config(self, config_file: Path | str) -> None:
        # get useful data out of json
        if type(config_file) is PosixPath:
            with open(config_file, "r") as file:
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
            self.conversion_data.extend(self.parse_file_data(file_data, processed_files))
            if Path(file_data["src"]).is_file():
                processed_files.append(Path(file_data["src"]))

    def parse_meta_data(self, meta_data: dict) -> None:
        self.domain = meta_data["domain"]
        logger.info(f"Getting config data for domain: {self.domain}\n")

        self.domain_synoptic_dst_part = Path(meta_data["domain_synoptic_dst"])
        self.acc_ui_support_dst_part = Path(meta_data["acc_ui_support_dst"])
        self.domain_ui_support_dst_part = Path(meta_data["domain_ui_support_dst"])

        self.domain_synoptic_dst_full = self.output_dir_path / meta_data["domain_synoptic_dst"]
        self.acc_ui_support_dst_full = self.output_dir_path / meta_data["domain_synoptic_dst"] / meta_data["acc_ui_support_dst"]
        self.domain_ui_support_dst_full = self.output_dir_path / meta_data["domain_synoptic_dst"] / meta_data["domain_ui_support_dst"]

        if "convert_dependencies" in meta_data:
            self.convert_dependencies = bool(meta_data["convert_dependencies"])

    def parse_file_data(
        self, file_data: dict, processed_files: list
    ) -> list[ConversionConfig]:
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
                message = "The 'new_filename' field cannot be used when src is given as a directory. Please check config file."
                logger.error(message)
                raise ValueError(message)

            if "include_subdirs" in file_data and file_data["include_subdirs"] is True:
                for file_paths in src_path_config.rglob("*.opi"):
                    src_file_paths.append(file_paths)

                    if support_module_name is not None:
                        recursive_dir = Path(support_module_name)
                    else:
                        recursive_dir = Path(src_path_config.name)

                    # We need to do some fancy path manipulation to recreate the old directory
                    # structure in the destination directory
                    if len(file_paths.parent.parts) > len(src_path_config.parts):
                        for subdir in file_paths.parent.parts[
                            len(src_path_config.parts) :
                        ]:
                            recursive_dir = recursive_dir / subdir

                        if (recursive_dir.parts[0], dst_path_partial / recursive_dir) not in self.domain_support_module_locations:
                            self.domain_support_module_locations.append((recursive_dir.parts[0], dst_path_partial / recursive_dir))

                    new_dst = dst_path_config / recursive_dir
                    dst_dir_paths.append(new_dst)
            else:
                for file_paths in src_path_config.glob("*.opi"):
                    if file_paths not in processed_files:
                        src_file_paths.append(file_paths)
                        dst_dir_paths.append(dst_path_config)
                    else:
                        logger.warning(
                            f"File {file_paths} has already been processed, skipping conversion."
                        )
        else:
            src_file_paths = [src_path_config]
            dst_dir_paths = [dst_path_config]

        for src_file_path, dst_dir_path in zip(
            src_file_paths, dst_dir_paths, strict=True
        ):
            new_conversion = ConversionConfig()
            new_conversion.src_file_path = src_file_path
            new_conversion.dst_dir_path = dst_dir_path
            if "new_filename" in file_data:
                new_conversion.dst_filename = file_data["new_filename"]
            if "macros" in file_data:
                new_conversion.macros = file_data["macros"]
            if "support_module_name" in file_data:
                new_conversion.support_module_name = support_module_name
            if "template_file" in file_data:
                template_file_path = Path(file_data["template_file"])
                if template_file_path.is_file():
                    new_conversion.template_file_path = template_file_path
                else:
                    template_file_path = Path.cwd() / "templates" / template_file_path
                if not template_file_path.is_file():
                    raise FileNotFoundError(f"Could not find template file {str(template_file_path)}")
                new_conversion.template_file_path = template_file_path
            if file_data["dst"] == "synoptic":
                new_conversion.synoptic = True
            new_conversions.append(new_conversion)

        return new_conversions

    def read_bob_file_contents(self, file_path: Path, conversion):
        with open(file_path, "r", encoding="utf-8") as fh:
            fxml = fh.read()
            as_dict = xmltodict.parse(fxml)
            conversion.all_phoebus_data = as_dict
            conversion.widget_data = as_dict["display"]["widget"]

    def write_bob_file_contents(self, file_path: Path, conversion):
        with open(file_path, "w") as fh:
            new_xml = xmltodict.unparse(conversion.all_phoebus_data, pretty=True)
            fh.write(new_xml)

    def fill_in_file_path_macros(self, string: str, macros) -> str:
        def replace(match):
            key = match.group(1)              # the ‘x’ inside ${x}
            return macros.get(key, match.group(0))   # default: leave unchanged

        resolved_path = re.sub(
            r"\$[\{\(]([^\}\)\s]+)[\}\)]",
            replace,
            str(string)
        )
        return resolved_path
    
    def search_widget_filepaths_recursive(self, widget, func: typing.Callable, widget_file_paths=None, macros=None):
        """This generic, recursive function takes a widget and searches for any references to filepaths
         these can be in multiple different widget fields and also in widgets within the widget etc
         When a filepath is found, it is passed into the passed func callable."""

        args = [arg for arg in [widget_file_paths, macros] if arg is not None]

        if not isinstance(widget, dict):
            return
        if "widget" in widget:
            for widget in widget["widget"]:
                self.search_widget_filepaths_recursive(widget, func, widget_file_paths, macros)
        if "tabs" in widget:
            for tab in widget["tabs"]["tab"]:
                # widget["tabs"]["tab"] can either be a single tab or a list of tabs, so
                # we have to handle this by checking the type of tab
                if type(tab) is str:
                    for child_widget in widget["tabs"]["tab"]["children"]["widget"]:
                        if type(child_widget) is str:
                            self.search_widget_filepaths_recursive(widget["tabs"]["tab"]["children"]["widget"], func, widget_file_paths, macros)
                            break
                        self.search_widget_filepaths_recursive(child_widget, func, widget_file_paths, macros)
                    break
                if "children" in tab and tab["children"] is not None:
                    for child_widget in tab["children"]["widget"]:
                        if type(child_widget) is str:
                            self.search_widget_filepaths_recursive(tab["children"]["widget"], func, widget_file_paths, macros)
                            break
                        self.search_widget_filepaths_recursive(child_widget, func, widget_file_paths, macros)
        if "symbols" in widget:
            for symbol_widget_name in widget["symbols"]:
                symbol_widget = widget["symbols"][symbol_widget_name]
                if symbol_widget != [None, None]:
                    if isinstance(symbol_widget, list):
                        for i, symbol_path in enumerate(symbol_widget):
                            if func(Path(symbol_path), *args, symbol=True):
                                symbol_widget[i] = func(Path(symbol_path), *args, symbol=True)
                    else:
                        # We only log when we find edm widget not when we later switch it
                        if func.__name__ == "append_new_filepath":
                            logger.warning(f"Warning, edm style symbol widget detected: {widget['name']}")
                        if func(Path(symbol_widget), *args, symbol=True):
                            widget["symbols"]["symbol"] = func(Path(symbol_widget), *args, symbol=True)
        if "file" in widget and widget["file"] is not None:
            if func(Path(widget["file"]), *args):
                widget["file"] = func(Path(widget["file"]), *args)
        if "opi_file" in widget and widget["opi_file"] is not None:
            if func(Path(widget["opi_file"]), widget["opi_file"], *args):
                widget["opi_file"] = func(Path(widget["opi_file"]), widget["opi_file"], *args)
        if "actions" in widget and widget["actions"] is not None:
            for action in widget["actions"]:
                if "path" in widget["actions"][action]:
                    if func(Path(widget["actions"][action]["path"]), *args):
                        widget["actions"][action]["path"] = func(Path(widget["actions"][action]["path"]), *args)
                elif "file" in widget["actions"][action]:
                    if func(Path(widget["actions"][action]["file"]), *args):
                        widget["actions"][action]["file"] = func(Path(widget["actions"][action]["file"]), *args)
        return widget_file_paths

    def get_widget_filepaths(self, widget, widget_file_paths):
        def append_new_filepath(path_string, widget_file_paths, symbol=False):
            widget_file_paths.append(path_string)
            return False
        return self.search_widget_filepaths_recursive(widget, append_new_filepath, widget_file_paths)

    def update_widget_filepaths(self, widget, macros):
        self.search_widget_filepaths_recursive(widget, self.switch_filepaths, macros)

    def get_required_support_modules(self, conversion: ConversionConfig, file_path: Path) -> None:
        widget_file_paths: list[Path] = []
        # Look for filepaths in xml
        for widget in conversion.widget_data:
            self.get_widget_filepaths(widget, widget_file_paths)

        # Only keep unique filepaths and fill in macros
        file_paths_unique = set()
        for file_path in set(widget_file_paths):
            file_paths_unique.add(Path(self.fill_in_file_path_macros(str(file_path), conversion.macros)))
                
        # If a support module has been requested and we are not already converting it,
        # then add it to the list of extra required support modules which we will attempt
        # to build later.
        for file_path in file_paths_unique:
            # Search through the filepath and remove any strings which dont look useful
            new_filepath = Path()
            for part in file_path.parts:
                strings_to_skip = ["..", ".", "images", "symbols"]
                if part not in strings_to_skip:
                    new_filepath = new_filepath / part
            file_path = new_filepath

            # If we only have 1 part left, it is probably the file itself which isnt a support module
            # so we move to the next one
            if len(file_path.parts) > 1:
                # The support module should be the second to last part
                support_module_name = file_path.parts[-2]
                if support_module_name in ACC_UI_SUPPORT_MODULE_LIST:
                    new_entry = (support_module_name, self.acc_ui_support_dst_part / support_module_name)
                    if new_entry not in self.acc_support_module_locations:
                        self.acc_support_module_locations.append(new_entry)
                else:
                    new_entry = (support_module_name, self.domain_ui_support_dst_part / support_module_name)
                    if new_entry not in self.domain_support_module_locations:
                        self.domain_support_module_locations.append(new_entry)

        logger.info(f"Required domain modules: {self.domain_support_module_locations}")
        logger.info(f"Required acc modules: {self.acc_support_module_locations}")
    
    def switch_filepaths(self, file_path, macros, symbol=False) -> str:
        "Takes an old file_path string and returns what the new file_path should be. This is done"
        "by getting the name of the support module from the old path and matching it with our data."
        file_path_string = str(file_path)
        all_support_modules = self.domain_support_module_locations + self.acc_support_module_locations
        # If the pathstring is in the current directory, eg file.bob, then no need to change it
        if len(file_path.parts) <=1:
            return file_path_string

        # If we have already updated the paths, dont do it again:
        if self.acc_ui_support_dst_part.parts[0] in file_path_string or self.domain_ui_support_dst_part.parts[0] in file_path_string or self.domain_synoptic_dst_part.parts[0] in file_path_string:
            return file_path_string

        file_path_string = self.fill_in_file_path_macros(file_path_string, macros)
        file_path = Path(file_path_string)
        if file_path.suffix == ".opi":
            file_name = file_path.with_suffix(".bob").name
        else:
            file_name=file_path.name

        new_filepath = Path()
        for part in file_path.parts:
            strings_to_skip = ["..", ".", "images", "symbols"]
            if part not in strings_to_skip:
                new_filepath = new_filepath / part
            elif part in ["images", "symbols"]:
                symbol=True
        support_module_name = new_filepath.parts[0]
        
        for data in all_support_modules:
            if data[0] == support_module_name:
                if symbol:
                    return str(Path(*data[1].parts[:-2]) / "symbols" / file_name)
                else:
                    return str(data[1] / file_name)
                
        logger.warning(f"Could not find support module for old path: {file_path_string}. Filepath unchanged.")
        return file_path_string
    
    def update_filepaths(self, conversion):
        # Look for filepaths in xml
        for widget in conversion.widget_data:
            self.update_widget_filepaths(widget, conversion.macros)

        conversion.all_phoebus_data["display"]["widget"] = conversion.widget_data

    def add_new_macros(
        self, conversion: ConversionConfig, macro_names: list[str], macro_values: list[str]
    ) -> None:
        """Add a list of macro name/values to the top level of the bob file."""

        if "macros" not in conversion.all_phoebus_data["display"]:
            conversion.all_phoebus_data["display"]["macros"] = {}

        macro_data = conversion.all_phoebus_data["display"]["macros"]

        for new_macro_name, new_macro_value in zip(
            macro_names, macro_values, strict=True
        ):
            for existing_macro_name, existing_macro_value in macro_data.items():
                if existing_macro_name == new_macro_name:
                    logging.warning(
                        f"An existing file macro is being overwritten: "
                        f"{existing_macro_name}:{existing_macro_value} -> "
                        f"{new_macro_name}:{new_macro_value}"
                    )
            macro_data[new_macro_name] = new_macro_value

        conversion.widget_data = conversion.all_phoebus_data["display"]["widget"]

    def handle_macros(self, file_path: Path, conversion: ConversionConfig) -> None:
        """Look for unique instances of a macro eg ${string} in the bob file. We ignore a small
        number of macros which are defined from other widget fields (MACRO_EXCEPTION_LIST).
        If a macro is found in a file but has not been defined in the ConversionConfig, then
        we log a warning."""

        new_macro_names = []
        new_macro_values = []

        with file_path.open("r", encoding="utf-8") as fh:
            content = fh.read()

        unique_identified_macros = set(
            re.findall(r"\$[\{\(]([^\}\)\s]+)[\}\)]", content)
        )
        logger.info(f"Found macros in file: {unique_identified_macros}")

        for macro in unique_identified_macros:
            # Some macros refer to internal Phoebus objects, so we dont resolve these
            if macro not in MACRO_EXCEPTION_LIST:
                if macro in conversion.macros.keys():
                    new_macro_names.append(macro)
                    new_macro_values.append(conversion.macros[macro])
                else:
                    # This macro has not been defined!
                    logger.warning(
                        f"Could not find definition for macro: '{macro}'. "
                        "Should this have been defined in your yaml config?"
                    )

        self.add_new_macros(conversion, new_macro_names, new_macro_values)

    def get_existing_support_module_filepath(self, support_module_name) -> str | None:
        dls_sw_support_modules = Path("/dls_sw/prod/R3.14.12.7/support/")
        version_list = []
        latest_file = Path("")
        # Look for the support module on dls_sw and get the path to the latest release
        for path in dls_sw_support_modules.iterdir():
            if path.name==support_module_name:
                for version in path.iterdir():
                    if version.is_dir():
                        version_list.append(version)
                latest_file = max([f for f in version_list], key=lambda item: item.stat().st_ctime)

        opi_dir_guess = latest_file / f"{support_module_name}App" / "opi" / "opi"
        if opi_dir_guess.is_dir():
            return str(opi_dir_guess)
        else:
            logger.error(f"Could not find {support_module_name} in {str(dls_sw_support_modules)}")
            return None

    def convert_extra_support_modules(self):
        all_support_modules = self.domain_support_module_locations + self.acc_support_module_locations

        if type(self.config_file) is PosixPath:
            with open(self.config_file, "r") as file:
                data = yaml.safe_load(file)
        else:
            data = self.config_file
        data["files"] = []

        existing_modules_paths = list(self.acc_ui_support_dst_full.iterdir())  + list(self.domain_ui_support_dst_full.iterdir())
        existing_module_names = [path.name for path in existing_modules_paths]
        # sm -> support module
        for sm_name, sm_file_path in all_support_modules:
            if sm_name not in existing_module_names:
                # Filter out any files which have been mistaken for support modules
                if sm_file_path.suffix == '':
                    sm_src_file_path = self.get_existing_support_module_filepath(sm_name)
                    if sm_src_file_path is not None:
                        if sm_name in ACC_UI_SUPPORT_MODULE_LIST:
                            data["files"].append({
                                'src': sm_src_file_path,
                                'dst': 'acc-ui-support',
                                'support_module_name': sm_name,
                                'include_subdirs': True
                            })
                        else:
                            data["files"].append({
                                'src': sm_src_file_path,
                                'dst': 'fe-ui-support',
                                'support_module_name': sm_name,
                                'include_subdirs': True
                            })
                    logger.info(f"Converting extra support module: {sm_name}")
        if len(data["files"]) > 0:
            self.get_config(data)
            self.convert()
        else:
            logger.info("Creating extra modules finished!")

    def convert(self) -> None:
        for conversion in self.conversion_data:
            logger.info(f"Converting {conversion.src_file_path}")
                                                                     
            # Create directories to place screens, this should probably be in opi_converter.py
            conversion.dst_dir_path.mkdir(parents=True, exist_ok=True)

            # Convert .boy to .bob
            converted_file = opi_converter.main(
                conversion.src_file_path,
                conversion.dst_dir_path,
                conversion.dst_filename,
                conversion.template_file_path
            )

            # Read in the widget data from the new bob file
            self.read_bob_file_contents(converted_file, conversion)

            # We need to define macros which were previously passed into the synoptic as script arguments
            if conversion.synoptic:
                self.handle_macros(converted_file, conversion)

            # Figure out which filepaths within bob files need updating and
            # update them to the new paths.
            self.get_required_support_modules(conversion, converted_file)
            self.update_filepaths(conversion)

            # Overwrite the bob file with the modified xml data
            self.write_bob_file_contents(converted_file, conversion)
            logger.info(f"Conversion saved to {converted_file}\n")

        # Get missing support module screens
        if self.convert_dependencies:
            self.convert_extra_support_modules()

def parse_arguments():
    """Parse command line arguments sent to virtac"""
    parser = ArgumentParser()
    parser.add_argument(
        "config_file",
        type=str,
        help="The yaml config for the conversion. This can either be a full path to a"
        " .yaml file or the name of one of the .yaml files in config/",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        required=False,
        type=str,
        help="The full path to the directory to output generated files to",
        default=Path.cwd() / "output",
    )
    parser.add_argument(
        "-d",
        "--debug",
        help="Enable debug logging",
        action="store_true",
        default=False,
    )
    args = parser.parse_args()

    config_file_path = Path(args.config_file)
    # If the user only supplied the name of a config file, then add the path to the
    # directort containing the config files
    if len(config_file_path.parts) == 1:
        config_file_path = Path.cwd() / "config" / config_file_path
    if args.debug:
        logger.setLevel(logging.DEBUG)

    return config_file_path, Path(args.output_dir)


def main():
    args = parse_arguments()
    logger.debug(f"Running screen conversion with arguments: {args}")
    converter = Converter(config_file_path=args[0], output_dir_path=args[1])
    converter.convert()


if __name__ == "__main__":
    main()
