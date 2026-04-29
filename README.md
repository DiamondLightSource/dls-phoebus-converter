[![CI](https://github.com/DiamondLightSource/dls-phoebus-converter/actions/workflows/ci.yml/badge.svg)](https://github.com/DiamondLightSource/dls-phoebus-converter/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/DiamondLightSource/dls-phoebus-converter/branch/main/graph/badge.svg)](https://codecov.io/gh/DiamondLightSource/dls-phoebus-converter)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

# dls_phoebus_converter

Converts Diamond cs-studio screens for use in Phoebus

The user provides a config.yaml file which is parsed by screen_converter.py. This generates a list of opi files which need converting. Each opi screen is converted by opi_converter.py and the final file is saved into the proper location within the new screen file layout for Diamond II.

What            | Where
:---:           | :---:
Source          | <https://github.com/DiamondLightSource/dls-phoebus-converter>
Docker          | `docker run ghcr.io/diamondlightsource/dls-phoebus-converter:latest`
Releases        | <https://github.com/DiamondLightSource/dls-phoebus-converter/releases>

This is where you should put some images or code snippets that illustrate
some relevant examples. If it is a library then you might put some
introductory code here:

```python
from dls_phoebus_converter import __version__

print(f"Hello dls_phoebus_converter {__version__}")
```

Or if it is a commandline tool then you might put some example commands here:

```
python -m dls_phoebus_converter --version
```
