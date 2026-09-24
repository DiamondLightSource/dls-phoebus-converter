"""Top level API.

.. data:: __version__
    :type: str

    Version number as calculated by https://github.com/pypa/setuptools_scm
"""

from ._version import __version__
from .opi_converter import convert_single_screen
from .screen_converter import convert_from_config

__all__ = ["__version__", "convert_from_config", "convert_single_screen"]
