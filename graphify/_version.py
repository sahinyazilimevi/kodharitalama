"""Installed-distribution version for kodharitalama.

The import package deliberately keeps its historical ``graphify`` name so
existing imports and editor integrations keep working, while the published
distribution is named ``kodharitalama``. Version lookups must therefore use
the distribution name, not ``__package__``.

Running directly from a source checkout (without installing the project)
has no distribution metadata; ``SOURCE_VERSION`` keeps diagnostics and cache
namespacing useful in that case.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

DISTRIBUTION_NAME = "kodharitalama"

# Keep in sync with pyproject.toml.
SOURCE_VERSION = "0.30.103"


def distribution_version(default: str | None = None) -> str | None:
    """Return the installed kodharitalama version.

    ``default`` is returned when the distribution metadata is absent (source
    checkout). Pass ``None`` explicitly to get ``None`` instead of a version.
    """
    try:
        return _dist_version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return default
