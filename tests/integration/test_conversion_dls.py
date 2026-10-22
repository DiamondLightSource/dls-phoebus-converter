"""Convert screens from the diamond filesystem and compare them to the golden master."""

import difflib
import filecmp
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import OUTPUT_DIR

# A clone of the golden master repo, which must be at GOLDEN_MASTER_COMMIT
GOLDEN_MASTER_DIR = Path("tests/golden_master")
GOLDEN_MASTER_COMMIT = "aece866bed7ebd9129332870f9ad3c47476b8b78"
REFERENCE_DIR = GOLDEN_MASTER_DIR / "front_ends"

IGNORE_SUFFIXES = [".html", "test*"]
IMAGE_SUFFIXES = [".png", ".svg"]

# The converter logs everything to stderr, so only the end of it is shown on failure.
# That is enough for a traceback, which is what a crashed conversion leaves behind.
STDERR_TAIL_LINES = 40

# A regeneration can leave hundreds of uncommitted changes in the golden master.
UNCOMMITTED_CHANGES_LISTED = 10


def get_image_hash(img: Path) -> str:
    "Get image hash, excluding metadata."

    cmd = [
        "identify",
        "-quiet",
        "-format",
        "'%#\n'",
        img,
    ]

    result = subprocess.run(cmd, capture_output=True, encoding="utf-8")

    if result.returncode != 0:
        raise Exception(
            f"Failed to get image hash for: {img} with errors:\n{result.stderr}"
        )

    return result.stdout


def compare_images(test: Path, ref: Path) -> str:
    if get_image_hash(test) != get_image_hash(ref):
        return f"Files {test} and {ref} differ"

    return ""


def compare_dirs(out_dir, ref_dir):
    """Recursively looks for differences between the freshly converted screens in
    out_dir and the reference screens in ref_dir"""
    all_left = []
    all_right = []
    all_diffs = []
    dcmp = filecmp.dircmp(out_dir, ref_dir, ignore=IGNORE_SUFFIXES, shallow=False)

    for file in dcmp.diff_files:
        if Path(file).suffix in IMAGE_SUFFIXES:
            diff = compare_images(out_dir / file, ref_dir / file)
            if diff:
                all_diffs.append(diff)

            continue

        try:
            with open(out_dir / file) as test, open(ref_dir / file) as ref:
                lines1 = test.readlines()
                lines2 = ref.readlines()
        except UnicodeDecodeError as e:
            # In order to fix tests for files that cannot be compared line-by-line, you
            # may need to ignore, add to IMAGE_SUFFIXES, or otherwise handle errors
            raise Exception(f"Cannot compare {file}") from e

        diff = difflib.unified_diff(lines1, lines2, fromfile=str(test), tofile=str(ref))
        diff_str = "".join(diff)
        if diff_str == "":
            raise Exception(f"Unexpected empty diff for {test} and {ref}")

        all_diffs.append(f"Files {test} and {ref} differ:\n{diff_str}")

    if dcmp.left_only:
        all_left.extend([out_dir / file for file in dcmp.left_only])

    if dcmp.right_only:
        all_right.extend([out_dir / file for file in dcmp.right_only])

    for common_dir in dcmp.common_dirs:
        new_dir1 = Path(out_dir) / Path(common_dir)
        new_dir2 = Path(ref_dir) / Path(common_dir)
        left, right, diff_list = compare_dirs(new_dir1, new_dir2)
        all_left.extend(left)
        all_right.extend(right)
        all_diffs.extend(diff_list)

    return all_left, all_right, all_diffs


def add_gitkeep_files(root: Path) -> None:
    """Add a .gitkeep to each empty directory under root.

    Git does not track empty directories, so we need to add this if we want to store
    generated files in a git repository.
    """
    for dir_path, dir_names, file_names in root.walk():
        if not dir_names and not file_names:
            (dir_path / ".gitkeep").touch()


def run_golden_master_git(*args: str) -> str:
    """Run git in the golden master clone, failing the test if git fails.

    Args:
        *args: The git subcommand and its arguments.

    Returns:
        The subcommand's stdout.
    """
    result = subprocess.run(
        ["git", "-C", str(GOLDEN_MASTER_DIR), *args],
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        pytest.fail(f"git {' '.join(args)} failed:\n{result.stderr}")

    return result.stdout


def check_golden_master() -> None:
    """Fail the test unless the golden master clone is ready to be compared against.

    The clone must be at GOLDEN_MASTER_COMMIT, with no uncommitted changes in
    front_ends/.
    """
    # Without its own .git, git would run in the converter repo instead
    if not (GOLDEN_MASTER_DIR / ".git").exists():
        pytest.fail(
            f"Clone the golden master repo to {GOLDEN_MASTER_DIR}/, as tests/README.md "
            "describes"
        )

    head = run_golden_master_git("rev-parse", "HEAD").strip()
    if head != GOLDEN_MASTER_COMMIT:
        pytest.fail(
            f"{GOLDEN_MASTER_DIR} is at {head}, not GOLDEN_MASTER_COMMIT. Fetch if "
            f"needed, then run:\n"
            f"git -C {GOLDEN_MASTER_DIR} checkout {GOLDEN_MASTER_COMMIT}"
        )

    changes = run_golden_master_git(
        "status", "--porcelain", "--", "front_ends"
    ).splitlines()
    if not changes:
        return

    listed = "\n".join(changes[:UNCOMMITTED_CHANGES_LISTED])
    if len(changes) > UNCOMMITTED_CHANGES_LISTED:
        listed += f"\n...and {len(changes) - UNCOMMITTED_CHANGES_LISTED} more"

    pytest.fail(
        f"Commit or stash the uncommitted changes in {REFERENCE_DIR}:\n{listed}"
    )


def test_front_ends(pytestconfig: pytest.Config) -> None:
    """Convert config/front_ends.yaml and compare the output with the golden master.

    This requires access to /dls_sw and the golden master clone, so is skipped without
    --run-dls.

    Args:
        pytestconfig: The pytest config, for --run-dls.
    """
    if not pytestconfig.getoption("--run-dls"):
        pytest.skip("needs --run-dls")

    check_golden_master()

    # Do conversion from /dls_sw
    cmd = [
        sys.executable,
        "-m",
        "dls_phoebus_converter",
        "-o",
        "test_output/",
        "-c",
        "config/front_ends.yaml",
    ]
    result = subprocess.run(
        cmd, stderr=subprocess.PIPE, encoding="utf-8", errors="replace"
    )

    add_gitkeep_files(OUTPUT_DIR)
    left, right, diffs = compare_dirs(OUTPUT_DIR, REFERENCE_DIR)
    if left or right or diffs:
        print(f"Found the following extra files generated by the conversion: {left}\n")
        print(f"Found the following missing files from the conversion: {right}\n")
        print("The following files have been unexpectedly modified:\n")
        if len(diffs) > 3:
            print("Too many to show")
        else:
            for diff in diffs:
                print(f"{diff}\n")

        if result.returncode != 0:
            tail = result.stderr.splitlines()[-STDERR_TAIL_LINES:]
            print(f"\nThe conversion exited {result.returncode}, ending with:\n")
            print("\n".join(tail))

        raise AssertionError("Found differences in the conversion.")
