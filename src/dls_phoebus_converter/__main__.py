"""Interface for ``python -m dls_phoebus_converter``."""

import logging
from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

from dls_phoebus_converter._version import __version__
from dls_phoebus_converter.logconfig import setup_logging
from dls_phoebus_converter.opi_converter import OpiConverter
from dls_phoebus_converter.screen_converter import ScreenConverter

__all__ = ["main"]


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
        "-c",
        "--config-file",
        required=False,
        default=None,
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
        "-s",
        "--single-screen",
        required=False,
        type=str,
        help="Optionally, pass the path to a single screen to convert. This should be "
        "passed instead of --config-file",
        default=None,
    )
    parser.add_argument(
        "-d",
        "--debug",
        help="Enable debug logging",
        action="store_true",
        default=False,
    )
    args = parser.parse_args(args)

    return args


def main(args: Sequence[str] | None = None) -> None:
    setup_logging()
    logger = logging.getLogger("dls_phoebus_converter")

    args = parse_arguments()

    logger.debug(f"Running screen conversion with arguments: {args}")

    if args.debug:
        logger.setLevel(logging.DEBUG)

    if args.single_screen is not None and args.config_file is not None:
        logging.error(
            "You cannot provide both a single-screen and a "
            "config_file argument. Exiting"
        )
        return

    if args.config_file is not None:
        config_file_path = Path(args.config_file)
        # If the user only supplied the name of a config file, then add the path to the
        # directory containing the example config files
        if len(config_file_path.parts) == 1:
            config_file_path = Path.cwd() / "config" / config_file_path
        converter = ScreenConverter(
            config_file_path=config_file_path, output_dir_path=Path(args.output_dir)
        )
        converter.convert()

    elif args.single_screen is not None:
        converter = OpiConverter(Path(args.single_screen), Path(args.output_dir))
        logger.info(f"Converting {converter.src_file_path}")
        # Create directories to place screens
        converter.dst_dir_path.mkdir(parents=True, exist_ok=True)
        # Convert .opi to .bob
        converter.convert()

    else:
        logging.error(
            "You must provide either a single-screen to convert or a "
            "config_file. Exiting"
        )
        return


if __name__ == "__main__":
    main()
