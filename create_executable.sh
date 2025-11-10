#!/bin/bash

output_name="linuxdeployqt-python-gui"
pyinstaller --noconfirm \
            --onefile \
            --windowed \
            --clean \
            --log-level=INFO \
            --name "$output_name" \
            --add-data "./gui:gui/" \
            --add-data "./logger:logger/" \
            --add-data "./tools:tools/" \
            --add-data "./linuxdeployqt-python-cli.py:." \
            --add-data "./linuxdeployqt-python-gui.py:." \
            --collect-submodules colorlog \
            --collect-submodules ansi2html \
            --hidden-import colorlog \
            --hidden-import colorlog.formatter \
            --hidden-import ansi2html \
            --hidden-import dataclasses \
            --hidden-import typing \
            --hidden-import subprocess \
            --hidden-import pathlib \
            --hidden-import json \
            --hidden-import re \
            --hidden-import shutil \
            --hidden-import glob \
            --hidden-import os \
            --hidden-import sys \
            "$output_name.py"
