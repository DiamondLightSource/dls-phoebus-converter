"""Convert the screens in tests/test_data/opi_files and compare the conversions to their
previous conversions in tests/test_data/bob_files."""

import subprocess
import sys
from pathlib import Path

from xmldiff import formatting, main

from conftest import OUTPUT_SRC

REFERENCE_DIR = Path("tests/test_data/bob_files/fe-services/synoptic/")
OUTPUT_DIR = OUTPUT_SRC / Path("fe-services/synoptic/")


def conversion_test(config_file, files_to_convert):
    diffs = []
    cmd = [
        sys.executable,
        "-m",
        "dls_phoebus_converter",
        "-o",
        OUTPUT_SRC,
        "-c",
        f"config/{config_file}",
    ]
    proc = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
    proc.wait()

    for file in files_to_convert:
        diff = main.diff_files(
            REFERENCE_DIR / file,
            OUTPUT_DIR / file,
            formatter=formatting.XmlDiffFormatter(
                normalize=formatting.WS_TAGS, pretty_print=True
            ),
        )
        if diff != "":
            diffs.append(
                f"Diff for files: {REFERENCE_DIR / file}, {OUTPUT_DIR / file}:\n{diff}"
            )
    return diffs


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
