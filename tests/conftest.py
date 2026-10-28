import logging
import shutil
from pathlib import Path

import pytest

from dls_phoebus_converter.logconfig import setup_logging

# The root directory into which the converter saves screens
OUTPUT_DIR = Path("test_output")

setup_logging()
logging.getLogger("dls_phoebus_converter").setLevel(logging.ERROR)


@pytest.fixture(autouse=True)
def output_directory():
    """Create output directory before each test and clean up after."""
    output_dir = OUTPUT_DIR
    if output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir()
