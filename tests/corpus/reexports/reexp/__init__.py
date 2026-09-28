"""Reexp: the API lives in private modules and is re-exported here."""

__version__ = "0.1.0"

import os
from shutil import get_terminal_size as get_terminal_size

from . import colors as colors
from ._impl import App as App
from ._impl import run as run
from ._impl import helper


def main() -> None:
    """Entry point defined in the package itself."""
    helper()
    run(App(os.getcwd()))
