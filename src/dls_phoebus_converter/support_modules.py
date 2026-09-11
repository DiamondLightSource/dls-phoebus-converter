"""Handles moving support modules screens from distributed locations to
the deployment locations."""

from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path, PosixPath
from typing import TYPE_CHECKING

import yaml

from dls_phoebus_converter.macros import fill_in_macros

if TYPE_CHECKING:
    from dls_phoebus_converter.opi_converter import OpiConverter
    from dls_phoebus_converter.screen_converter import ScreenConverter
from dls_phoebus_converter.utilities import search_widget_filepaths

ACC_UI_SUPPORT_MODULE_LIST = [
    "devIocStats",
    "digitelMpc",
    "mks937a",
    "mks937b",
    "mks937$(mks_type)",
    "mks937$(mksType)",
    "mpsPermit",
    "rga",
    "TimingTemplates",
]

logger = logging.getLogger("dls_phoebus_converter")


class UnpinnedModuleAction(StrEnum):
    """What to do with a support module that has no pinned release in the config."""

    LATEST = "latest"
    ERROR = "error"


def handle_support_modules(sc: ScreenConverter, oc: OpiConverter):
    """Figure out which filepaths within bob files need updating and
    update them to the new paths for the DII screen deployment structure."""

    find_required_support_modules(sc, oc)
    update_filepaths(sc, oc)


def find_required_support_modules(sc: ScreenConverter, oc: OpiConverter) -> None:
    """Update the ScreenConverters list of required support modules based on
    references to support modules found in the screen."""

    widget_file_paths: list[Path] = []
    # Look for filepaths in xml
    for widget in oc.bob_data.findall(".//widget"):
        search_widget_filepaths(sc, oc, widget, append_new_filepath, widget_file_paths)

    # Only keep unique filepaths and fill in macros
    file_paths_unique = set()
    for file_path in set(widget_file_paths):
        resolved_path = fill_in_macros(str(file_path), oc.macros)
        if resolved_path is not None:
            file_paths_unique.add(Path(resolved_path))

    # If a support module has been requested and we are not already converting it,
    # then add it to the list of extra required support modules which we will
    # attempt to build later.
    for file_path in file_paths_unique:
        # Search through the filepath and remove any strings which dont look useful
        new_filepath = Path()
        for part in file_path.parts:
            strings_to_skip = ["..", ".", "images", "symbols", "symbol"]
            if part not in strings_to_skip:
                new_filepath = new_filepath / part
        file_path = new_filepath

        # If we only have 1 part left, it is probably the file itself which isnt a
        # support module so we move to the next one
        if len(file_path.parts) > 1:
            support_module_name = file_path.parts[0]
            # check if our "support_module" is actually just a folder at the same level
            if support_module_name in [
                f.name for f in oc.src_file_path.parent.iterdir() if f.is_dir()
            ]:
                continue

            if support_module_name in ACC_UI_SUPPORT_MODULE_LIST:
                new_entry = (
                    support_module_name,
                    sc.acc_ui_support_bob_dst_part / support_module_name,
                )
                if new_entry not in sc.acc_support_module_locations:
                    sc.acc_support_module_locations.append(new_entry)
            else:
                new_entry = (
                    support_module_name,
                    sc.domain_ui_support_bob_dst_part / support_module_name,
                )
                if new_entry not in sc.domain_support_module_locations:
                    sc.domain_support_module_locations.append(new_entry)

    logger.info(f"Required domain modules: {sc.domain_support_module_locations}")
    logger.info(f"Required acc modules: {sc.acc_support_module_locations}")


def append_new_filepath(sc, oc, path_string, widget_file_paths, symbol=False):
    widget_file_paths.append(path_string)
    return False


def update_filepaths(sc: ScreenConverter, oc: OpiConverter):
    """Replace all filepaths in the element tree"""
    for widget in oc.bob_data.findall(".//widget"):
        search_widget_filepaths(sc, oc, widget, switch_filepaths, oc.macros)


def switch_filepaths(
    sc: ScreenConverter,
    oc: OpiConverter,
    file_path: Path,
    macros: dict[str, str] | None = None,
    symbol: bool = False,
) -> str:
    "Takes an old file_path string and returns what the new file_path should be."
    "This is done by getting the name of the support module from the old path and"
    "matching it with our data. We first look for the support module by guessing"
    "its name from the file_path string. If we cant deduce the support module from"
    "the file_path, then we guess that the file is somewhere in our own support module"

    support_module_name = None
    stripped_file_path = Path()
    all_support_modules = (
        sc.domain_support_module_locations + sc.acc_support_module_locations
    )

    # If the pathstring is in the current directory, eg file.bob, then no need to
    # change it
    if len(file_path.parts) <= 1:
        return str(file_path)

    # If we have already updated the paths, dont do it again
    if sc.acc_ui_support_bob_dst_part.parts[0] in str(
        file_path
    ) or sc.domain_ui_support_bob_dst_part.parts[0] in str(file_path):
        return str(file_path)

    if macros is not None:
        file_path = Path(fill_in_macros(str(file_path), macros))

    if file_path.suffix == ".opi":
        file_path = file_path.with_suffix(".bob")

    if file_path.suffix in [".png", ".svg", ".gif", ".jpeg"]:
        symbol = True

    for part in file_path.parts:
        strings_to_skip = ["..", "."]
        if part not in strings_to_skip:
            stripped_file_path = stripped_file_path / part

    # Look to see if the first part of the stripped filepath is a support module
    # which we recognise. If it is then, we will be updating the filepath to point
    # to the new location for this support module. Otherwise, the stripped
    # filepath is probably a relative path to a folder within our own support module.
    for data in all_support_modules:
        if data[0] == stripped_file_path.parts[0]:
            support_module_name = stripped_file_path.parts[0]
            subdir_structure = Path(*stripped_file_path.parts[1:]).parent

    if support_module_name is None:
        support_module_name = oc.support_module_name
        subdir_structure = stripped_file_path.parent

    for data in all_support_modules:
        if data[0] == support_module_name:
            if symbol:
                # data[1] stores the path to bob/support_module, we want the symbols
                # which is data[1]/../symbols
                path_to_support_modules = (
                    oc.path_to_top / data[1].parent.parent / "symbols"
                )
                return str(
                    path_to_support_modules / support_module_name / file_path.name
                )
            else:
                path_to_support_modules = oc.path_to_top / data[1].parent
                # we care about keeping the support module structure for bob files
                # but not for symbols
                return str(
                    path_to_support_modules
                    / support_module_name
                    / subdir_structure
                    / file_path.name
                )

    logger.warning(
        f"Could not find support module for old path: {str(file_path)}. Filepath "
        "unchanged."
    )
    return str(file_path)


def get_existing_support_module_filepath(
    sc: ScreenConverter, support_module_name: str
) -> str | None:
    """Look for a support module in /dls_sw and get the path to its screens.

    Args:
        sc: The running conversion, holding the pinned releases and how to handle
            modules without one.
        support_module_name: Name of the support module to look for.

    Returns:
        The path to the screen directory of the chosen release, or None if the module
        is not in /dls_sw or that release holds no screens.
    """

    dls_sw_support_modules = Path("/dls_sw/prod/R3.14.12.7/support/")
    module_dir = dls_sw_support_modules / support_module_name
    if not module_dir.is_dir():
        logger.error(
            f"Could not find {support_module_name} in {str(dls_sw_support_modules)}"
        )
        return None

    release_dir = get_support_module_release(sc, support_module_name, module_dir)

    opi_dir_guess = release_dir / f"{support_module_name}App" / "opi" / "opi"
    if not opi_dir_guess.is_dir():
        logger.error(
            f"Could not find screens for {support_module_name} in {release_dir}"
        )
        return None

    return str(opi_dir_guess)


def get_support_module_release(
    sc: ScreenConverter, support_module_name: str, module_dir: Path
) -> Path:
    """Pick which release of a support module to convert from.

    Releases pinned in the config are used as given. An unpinned module falls back to
    the newest release on disk, and under UnpinnedModuleAction.ERROR is also recorded
    so that report_unpinned_modules can list them all at the end of the run.

    Args:
        sc: The running conversion, holding the pinned releases and how to handle
            modules without one.
        support_module_name: Name of the support module being resolved.
        module_dir: The module's directory in /dls_sw, holding one dir per release.

    Returns:
        The path to the chosen release directory.

    Raises:
        ValueError: If the release pinned for this module is not in /dls_sw.
    """

    pinned_release = sc.dependency_versions.get(support_module_name)
    if pinned_release is not None:
        release_dir = module_dir / str(pinned_release)
        if not release_dir.is_dir():
            error_msg = (
                f"Release {pinned_release} pinned for support module "
                f"{support_module_name} in the config file does not exist: "
                f"{release_dir}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        return release_dir

    if sc.on_unpinned_module is UnpinnedModuleAction.ERROR:
        sc.unpinned_modules_found.add(support_module_name)

    releases = [path for path in module_dir.iterdir() if path.is_dir()]
    return max(releases, key=lambda release: release.stat().st_ctime)


def report_unpinned_modules(sc: ScreenConverter) -> None:
    """Fail the conversion if any support module was resolved without a pinned release.

    Does nothing unless the config asked for UnpinnedModuleAction.ERROR. Every unpinned
    module is named in a single message.

    Args:
        sc: The finished conversion.

    Raises:
        ValueError: If any support module was resolved without a pinned release.
    """

    if not sc.unpinned_modules_found:
        return

    error_msg = (
        "The config file asks for on_unpinned_module: "
        f"{UnpinnedModuleAction.ERROR}, but these support modules have no pinned "
        "release and were converted from the newest release on disk: "
        f"{', '.join(sorted(sc.unpinned_modules_found))}. Add them to the dependencies "
        "field of the config file."
    )
    logger.error(error_msg)
    raise ValueError(error_msg)


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

    existing_modules_paths = list(sc.acc_ui_support_bob_dst_full.iterdir()) + list(
        sc.domain_ui_support_bob_dst_full.iterdir()
    )
    existing_module_names = [path.name for path in existing_modules_paths]
    # sm -> support module
    for sm_name, sm_file_path in all_support_modules:
        if sm_name not in existing_module_names:
            # Filter out any files which have been mistaken for support modules
            if sm_file_path.suffix == "":
                sm_src_file_path = get_existing_support_module_filepath(sc, sm_name)
                if sm_src_file_path is not None:
                    dst = "fe-ui-support"
                    if sm_name in ACC_UI_SUPPORT_MODULE_LIST:
                        dst = "acc-ui-support"

                    data["files"].append(
                        {
                            "src": sm_src_file_path,
                            "dst": dst,
                            "support_module_name": sm_name,
                            "include_subdirs": True,
                        }
                    )

                    logger.info(f"Converting extra support module: {sm_name}")

    if len(data["files"]) > 0:
        sc.get_config(data)
        sc.convert_screens()
    else:
        logger.info("Creating extra modules finished!")
