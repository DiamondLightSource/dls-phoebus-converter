"""Run the Phoebus converter over batches of .opi files."""

import itertools
import logging
import re
import subprocess
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PHOEBUS_SH_FILE_PATH = "/dls_sw/deploy-tools/modules/phoebus/dev/entrypoints/phoebus"

logger = logging.getLogger("dls_phoebus_converter")

# Screens are converted in batches to avoid container/phoebus overhead. Capped so that a
# long run reports progress as it goes, rather than going quiet for minutes at a time.
PHOEBUS_BATCH_SIZE = 100

# Batches run concurrently. Each one is a separate container using ~470MB, so the limit
# may be cores rather than memory.
PHOEBUS_WORKERS = 4


def run_phoebus_converter(
    opi_file_paths: list[Path], output_dir_path: Path
) -> set[str]:
    """Convert .opi files to .bob with the Phoebus converter.

    Each output is named after its input, so the inputs must have distinct names.

    Args:
        opi_file_paths: The .opi files to convert.
        output_dir_path: Directory the converter writes the .bob files to.

    Returns:
        The filenames the converter reported it could not convert. It still writes an
        empty .bob for these, so they cannot be found by looking for a missing file.
    """

    batches = itertools.batched(opi_file_paths, PHOEBUS_BATCH_SIZE, strict=False)

    failed_file_names: set[str] = set()
    # Threads rather than processes: each one only waits on its own converter
    # subprocess, so almost no time is spent holding the GIL
    with ThreadPoolExecutor(max_workers=PHOEBUS_WORKERS) as executor:
        # Each batch becomes one run of the converter, read back as it finishes
        futures = [
            executor.submit(run_phoebus_batch, batch, output_dir_path)
            for batch in batches
        ]
        for future in as_completed(futures):
            failed_file_names.update(future.result())

    return failed_file_names


def run_phoebus_batch(
    opi_file_paths: Sequence[Path], output_dir_path: Path
) -> set[str]:
    """Run the Phoebus converter once over a batch of .opi files.

    Args:
        opi_file_paths: The .opi files to convert in this batch.
        output_dir_path: Directory the converter writes the .bob files to.

    Returns:
        The filenames the converter reported it could not convert.
    """

    convert_command = [
        PHOEBUS_SH_FILE_PATH,
        "-main",
        "org.csstudio.display.builder.model.Converter",
        "-output",
        str(output_dir_path),
        *[str(path) for path in opi_file_paths],
    ]
    logger.info(f"Running the Phoebus converter on {len(opi_file_paths)} screens")

    result = subprocess.run(convert_command, capture_output=True, encoding="utf-8")

    # The converter is very verbose, so it is logged at the DEBUG level
    for line in result.stderr.split("\n"):
        if line:
            logger.debug(f"Phoebus - {line}")

    return {
        Path(reported).name
        for reported in re.findall(r"Cannot convert (\S+)", result.stderr)
    }
