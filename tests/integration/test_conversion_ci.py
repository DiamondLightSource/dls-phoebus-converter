"""Convert the screens in tests/test_data/opi_files and compare the conversions to their
previous conversions in tests/test_data/bob_files."""

import difflib
import subprocess
import sys
from pathlib import Path

from conftest import OUTPUT_SRC

REFERENCE_DIR = Path("tests/test_data/bob_files/fe-services/synoptic/")
OUTPUT_DIR = OUTPUT_SRC / Path("fe-services/synoptic/")


def conversion_test(config_file, files_to_convert):
    diff_strings = []
    cmd = [
        sys.executable,
        "-m",
        "dls_phoebus_converter",
        "-o",
        OUTPUT_SRC,
        f"config/{config_file}",
    ]
    proc = subprocess.Popen(cmd)
    proc.wait()

    for file in files_to_convert:
        with open(OUTPUT_DIR / file) as test, open(REFERENCE_DIR / file) as ref:
            lines1 = test.readlines()
            lines2 = ref.readlines()
        diff = difflib.unified_diff(lines1, lines2, fromfile=str(test), tofile=str(ref))
        diff_str = "".join(diff)
        if diff_str != "":
            diff_strings.append(diff_str)
    return diff_strings


def test_single_conversion():
    """Run the conversion for example1.yaml, this tests the conversion of a single opi
    file. Compare the results to our reference data, failing if they differ."""

    files_to_convert = [
        "FE12I.bob",
    ]

    diff_strings = conversion_test("example1.yaml", files_to_convert)

    if len(diff_strings) != 0:
        print("The following files have been unexpectedly modified:\n")
        for diff_string in diff_strings:
            print(f"{diff_string}\n")
        raise AssertionError(
            f"{len(diff_strings)} files have been unexpectedly modified."
        )


def test_representative_conversion():
    """Run the conversion for example3.yaml, this tests a fairly complete representation
    ofthe features of the converter. Compare the results to our reference data, failing
    if they differ."""

    files_to_convert = [
        "FE09I.bob",
        "FE22B.bob",
        "FE24B.bob",
        "fe-ui-support/bob/common/plc/absb_temps_fe22b.bob",
    ]

    diff_strings = conversion_test("example3.yaml", files_to_convert)

    if len(diff_strings) != 0:
        print("The following files have been unexpectedly modified:\n")
        for diff_string in diff_strings:
            print(f"{diff_string}\n")
        raise AssertionError(
            f"{len(diff_strings)} files have been unexpectedly modified."
        )
