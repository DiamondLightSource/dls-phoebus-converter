import logging
import shutil
from pathlib import Path

import pytest

from dls_phoebus_converter.logconfig import setup_logging

# The root directory into which the converter saves screens
OUTPUT_SRC = Path("test_output")
# Stores screens downloaded from the webserver
REFERENCE_DIR = Path("test_output_ref")

setup_logging()
logging.getLogger("dls_phoebus_converter").setLevel(logging.ERROR)


@pytest.fixture(autouse=True)
def output_directory():
    """Create output directory before each test and clean up after."""
    output_dir = OUTPUT_SRC
    if output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir()


@pytest.fixture()
def ref_output_directory():
    """Create directory to copy dls reference data into before each test and clean up
    after."""
    output_dir = REFERENCE_DIR
    if output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir()
