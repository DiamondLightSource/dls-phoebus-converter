import subprocess
import sys

from dls_phoebus_converter import __version__


def test_cli_version():
    cmd = [sys.executable, "-m", "dls_phoebus_converter", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__
