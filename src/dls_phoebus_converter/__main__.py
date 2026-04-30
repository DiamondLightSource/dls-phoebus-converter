"""Interface for ``python -m dls_phoebus_converter``."""

import logging
from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

from dls_phoebus_converter._version import __version__
from dls_phoebus_converter.logconfig import setup_logging
from dls_phoebus_converter.screen_converter import Converter

__all__ = ["main"]

setup_logging()
logger = logging.getLogger("dls_phoebus_converter")


def parse_arguments(args: Sequence[str] | None = None) -> None:
    """Parse command line arguments sent to virtac"""
    parser = ArgumentParser()
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=__version__,
    )
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
    args = parser.parse_args(args)

    config_file_path = Path(args.config_file)
    # If the user only supplied the name of a config file, then add the path to the
    # directort containing the config files
    if len(config_file_path.parts) == 1:
        config_file_path = Path.cwd() / "config" / config_file_path
    if args.debug:
        logger.setLevel(logging.DEBUG)

    return config_file_path, Path(args.output_dir)


def main(args: Sequence[str] | None = None) -> None:
    args = parse_arguments()
    logger.debug(f"Running screen conversion with arguments: {args}")
    converter = Converter(config_file_path=args[0], output_dir_path=args[1])
    converter.convert()


if __name__ == "__main__":
    main()
