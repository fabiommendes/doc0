"""Private implementation."""


class App:
    """An application."""

    def __init__(self, name: str) -> None:
        self.name = name


def run(app: App) -> None:
    """Run an application."""


def helper() -> None:
    """Imported without `as`: not part of the public API."""
