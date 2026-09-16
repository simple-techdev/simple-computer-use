"""Shim so `pip install -e .` works with older pip; real metadata lives in
pyproject.toml."""

from setuptools import setup

setup()
