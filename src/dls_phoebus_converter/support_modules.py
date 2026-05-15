"""Handles moving support modules screens from distributed locations to
the deployment locations."""

from __future__ import annotations

import logging
from pathlib import Path, PosixPath
from typing import TYPE_CHECKING

import yaml
from lxml.etree import Element

from dls_phoebus_converter.logconfig import setup_logging
from dls_phoebus_converter.macros import fill_in_file_path_macros

if TYPE_CHECKING:
    from dls_phoebus_converter.screen_converter import ScreenConverter
from dls_phoebus_converter.utilities import search_widget_filepaths

if TYPE_CHECKING:
    from dls_phoebus_converter.opi_converter import OpiConverter

ACC_UI_SUPPORT_MODULE_LIST = [
    "devIocStats",
    "digitelMpc",
    "mks937a",
    "mks937b",
    "mpsPermit",
    "rga",
    "TimingTemplates",
]

if not logging.getLogger("dls_phoebus_converter"):
    setup_logging()
logger = logging.getLogger("dls_phoebus_converter")


def handle_support_modules(sc: ScreenConverter, oc: OpiConverter):
    # Figure out which filepaths within bob files need updating and
    # update them to the new paths.
    get_required_support_modules(sc, oc)
    # Support module paths are relative and so don't need to have their paths
    # updated
    if oc.support_module_name is None:
        update_filepaths(sc, oc)


def get_widget_filepaths(sc, widget: Element, widget_file_paths):
    def append_new_filepath(sc, path_string, widget_file_paths, symbol=False):
        widget_file_paths.append(path_string)
        return False

    return search_widget_filepaths(sc, widget, append_new_filepath, widget_file_paths)


def update_widget_filepaths(sc, widget, macros):
    search_widget_filepaths(sc, widget, switch_filepaths, macros)


def get_required_support_modules(sc: ScreenConverter, oc: OpiConverter) -> None:
    widget_file_paths: list[Path] = []
    # Look for filepaths in xml
    for widget in oc.bob_data.findall(".//widget"):
        get_widget_filepaths(sc, widget, widget_file_paths)

    # Only keep unique filepaths and fill in macros
    file_paths_unique = set()
    for file_path in set(widget_file_paths):
        file_paths_unique.add(Path(fill_in_file_path_macros(str(file_path), oc.macros)))

    # If a support module has been requested and we are not already converting it,
    # then add it to the list of extra required support modules which we will
    # attempt to build later.
    for file_path in file_paths_unique:
        # Search through the filepath and remove any strings which dont look useful
        new_filepath = Path()
        for part in file_path.parts:
            strings_to_skip = ["..", ".", "images", "symbols"]
            if part not in strings_to_skip:
                new_filepath = new_filepath / part
        file_path = new_filepath

        # If we only have 1 part left, it is probably the file itself which isnt a
        # support module so we move to the next one
        if len(file_path.parts) > 1:
            # The support module should be the second to last part
            support_module_name = file_path.parts[-2]
            if support_module_name in ACC_UI_SUPPORT_MODULE_LIST:
                new_entry = (
                    support_module_name,
                    sc.acc_ui_support_dst_part / support_module_name,
                )
                if new_entry not in sc.acc_support_module_locations:
                    sc.acc_support_module_locations.append(new_entry)
            else:
                new_entry = (
                    support_module_name,
                    sc.domain_ui_support_dst_part / support_module_name,
                )
                if new_entry not in sc.domain_support_module_locations:
                    sc.domain_support_module_locations.append(new_entry)

    logger.info(f"Required domain modules: {sc.domain_support_module_locations}")
    logger.info(f"Required acc modules: {sc.acc_support_module_locations}")


def switch_filepaths(sc: ScreenConverter, file_path, macros=None, symbol=False) -> str:
    "Takes an old file_path string and returns what the new file_path should be."
    "This is done by getting the name of the support module from the old path and"
    "matching it with our data."
    file_path_string = str(file_path)
    all_support_modules = (
        sc.domain_support_module_locations + sc.acc_support_module_locations
    )
    # If the pathstring is in the current directory, eg file.bob, then no need to
    # change it
    if len(file_path.parts) <= 1:
        return file_path_string

    # If we have already updated the paths, dont do it again:
    if (
        sc.acc_ui_support_dst_part.parts[0] in file_path_string
        or sc.domain_ui_support_dst_part.parts[0] in file_path_string
        or sc.domain_synoptic_dst_part.parts[0] in file_path_string
    ):
        return file_path_string

    if macros is not None:
        file_path_string = fill_in_file_path_macros(file_path_string, macros)
    file_path = Path(file_path_string)
    if file_path.suffix == ".opi":
        file_name = file_path.with_suffix(".bob").name
    else:
        file_name = file_path.name

    new_filepath = Path()
    for part in file_path.parts:
        strings_to_skip = ["..", ".", "images", "symbols"]
        if part not in strings_to_skip:
            new_filepath = new_filepath / part
        elif part in ["images", "symbols"]:
            symbol = True
    support_module_name = "-".join(new_filepath.parts[:-1])

    for data in all_support_modules:
        if data[0] == support_module_name:
            if symbol:
                return str(Path(*data[1].parts[:-2]) / "symbols" / file_name)
            else:
                return str(data[1] / file_name)

    logger.warning(
        f"Could not find support module for old path: {file_path_string}. Filepath "
        "unchanged."
    )
    return file_path_string


def update_filepaths(sc, oc: OpiConverter):
    # Look for filepaths in xml
    for widget in oc.bob_data.findall(".//widget"):
        update_widget_filepaths(sc, widget, oc.macros)


def get_existing_support_module_filepath(support_module_name) -> str | None:
    """Look for a support module in /dls_sw and get the path to the latest release
    of the support module."""

    dls_sw_support_modules = Path("/dls_sw/prod/R3.14.12.7/support/")
    version_list = []
    latest_file = Path("")
    for path in dls_sw_support_modules.iterdir():
        if path.name == support_module_name:
            for version in path.iterdir():
                if version.is_dir():
                    version_list.append(version)
            latest_file = max(list(version_list), key=lambda item: item.stat().st_ctime)

    opi_dir_guess = latest_file / f"{support_module_name}App" / "opi" / "opi"
    if opi_dir_guess.is_dir():
        return str(opi_dir_guess)
    else:
        logger.error(
            f"Could not find {support_module_name} in {str(dls_sw_support_modules)}"
        )
        return None


def convert_extra_support_modules(sc: ScreenConverter):
    # wipe old conversion data as these are all finished
    sc.conversion_data = []

    all_support_modules = (
        sc.domain_support_module_locations + sc.acc_support_module_locations
    )

    if type(sc.config_file) is PosixPath:
        with open(sc.config_file) as file:
            data = yaml.safe_load(file)
    else:
        data = sc.config_file
    data["files"] = []

    existing_modules_paths = list(sc.acc_ui_support_dst_full.iterdir()) + list(
        sc.domain_ui_support_dst_full.iterdir()
    )
    existing_module_names = [path.name for path in existing_modules_paths]
    # sm -> support module
    for sm_name, sm_file_path in all_support_modules:
        if sm_name not in existing_module_names:
            # Filter out any files which have been mistaken for support modules
            if sm_file_path.suffix == "":
                sm_src_file_path = get_existing_support_module_filepath(sm_name)
                if sm_src_file_path is not None:
                    if sm_name in ACC_UI_SUPPORT_MODULE_LIST:
                        data["files"].append(
                            {
                                "src": sm_src_file_path,
                                "dst": "acc-ui-support",
                                "support_module_name": sm_name,
                                "include_subdirs": True,
                            }
                        )
                    else:
                        data["files"].append(
                            {
                                "src": sm_src_file_path,
                                "dst": "fe-ui-support",
                                "support_module_name": sm_name,
                                "include_subdirs": True,
                            }
                        )
                logger.info(f"Converting extra support module: {sm_name}")
    if len(data["files"]) > 0:
        sc.get_config(data)
        sc.convert()
    else:
        logger.info("Creating extra modules finished!")
