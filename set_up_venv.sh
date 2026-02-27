#!/bin/bash

# This application supports python 3.10 and above only.
PYTHON_VERSION="3.11"

module load python/${PYTHON_VERSION}
python -m venv .venv
module unload python/${PYTHON_VERSION}
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Required to use the inherent Phoebus converter
module load java/17
