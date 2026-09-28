"""Interface for ``python -m dls_phoebus_converter``."""

import logging
from pathlib import Path
from typing import Annotated

import typer

from dls_phoebus_converter._version import __version__
from dls_phoebus_converter.logconfig import setup_logging
from dls_phoebus_converter.opi_converter import convert_single_screen
from dls_phoebus_converter.screen_converter import convert_from_config

__all__ = ["main"]

app = typer.Typer(add_completion=False)


def version_callback(value: bool) -> None:
    """Print the version and exit, for the eager ``--version`` option.

    Args:
        value: Whether ``--version`` was given.

    Raises:
        typer.Exit: Once the version has been printed.
    """
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def convert(
    config_file: Annotated[
        Path | None,
        typer.Option(
            "-c",
            "--config-file",
            help="The yaml config for the conversion. This can either be a full path "
            "to a .yaml file or the name of one of the .yaml files in config/",
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output-dir",
            help="The full path to the directory to output generated files to",
            show_default="./output",
        ),
    ] = None,
    single_screen: Annotated[
        Path | None,
        typer.Option(
            "-s",
            "--single-screen",
            help="Optionally, pass the path to a single screen to convert. This should "
            "be passed instead of --config-file",
        ),
    ] = None,
    debug: Annotated[
        bool,
        typer.Option("-d", "--debug", help="Enable debug logging"),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "-v",
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show the version and exit",
        ),
    ] = False,
) -> None:
    """Convert Diamond cs-studio screens for use in Phoebus."""
    if single_screen is not None and config_file is not None:
        raise typer.BadParameter(
            "Cannot convert both a config file and a single screen",
            param_hint="--config-file / --single-screen",
        )

    if single_screen is None and config_file is None:
        raise typer.BadParameter(
            "Must provide either a config file or a single screen to convert",
            param_hint="--config-file / --single-screen",
        )

    setup_logging()
    logger = logging.getLogger("dls_phoebus_converter")

    if debug:
        logger.setLevel(logging.DEBUG)

    if output_dir is None:
        output_dir = Path.cwd() / "output"

    logger.debug(
        f"Running screen conversion with arguments: config_file={config_file}, "
        f"output_dir={output_dir}, single_screen={single_screen}, debug={debug}"
    )

    if config_file is not None:
        # If the user only supplied the name of a config file, then add the path to the
        # directory containing the example config files
        if len(config_file.parts) == 1:
            config_file = Path.cwd() / "config" / config_file
        convert_from_config(config_file, output_dir)

    elif single_screen is not None:
        convert_single_screen(single_screen, output_dir)


def main() -> None:
    """Run the command line interface."""
    app()


if __name__ == "__main__":
    main()
