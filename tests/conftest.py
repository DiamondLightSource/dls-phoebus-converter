import logging
import shutil
from pathlib import Path

import pytest

from dls_phoebus_converter.logconfig import setup_logging

# The root directory into which the converter saves screens
OUTPUT_DIR = Path("test_output")

setup_logging()
logging.getLogger("dls_phoebus_converter").setLevel(logging.ERROR)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add the --run-dls option.

    Args:
        parser: The pytest command line parser.
    """
    parser.addoption(
        "--run-dls",
        action="store_true",
        help="run test_front_ends, which needs /dls_sw and tests/golden_master/",
    )


@pytest.fixture(autouse=True)
def output_directory():
    """Create output directory before each test and clean up after."""
    output_dir = OUTPUT_DIR
    if output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir()
