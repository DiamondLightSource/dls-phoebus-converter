import shutil
from pathlib import Path

import pytest

# The root directory into which the converter saves screens
OUTPUT_SRC = Path("test_output")
# Stores screens downloaded from the webserver
REFERENCE_DIR = Path("test_output_ref")


@pytest.fixture(autouse=True)
def output_directory():
    """Create output directory before each test and clean up after."""
    output_dir = OUTPUT_SRC
    output_dir.mkdir(exist_ok=True)

    yield

    # Cleanup after test
    if output_dir.exists():
        shutil.rmtree(output_dir)


@pytest.fixture()
def ref_output_directory():
    """Create directory to copy dls reference data into before each test and clean up
    after."""
    output_dir = REFERENCE_DIR
    output_dir.mkdir(exist_ok=True)

    yield

    # Cleanup after test
    if output_dir.exists():
        shutil.rmtree(output_dir)
