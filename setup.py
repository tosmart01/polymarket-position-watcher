"""Setup shim that mirrors metadata from pyproject.toml (uv style)."""
from __future__ import annotations

from pathlib import Path
import shutil

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback when packaging w/ older Python
    import tomli as tomllib  # type: ignore

from setuptools import find_packages, setup

HERE = Path(__file__).parent
PYPROJECT = tomllib.loads((HERE / "pyproject.toml").read_text())
PROJECT = PYPROJECT.get("project", {})
DEPENDENCIES = PROJECT.get("dependencies", [])
PYTHON_REQUIRES = PROJECT.get("requires-python", ">=3.11")
README_PATH = HERE / PROJECT.get("readme", "README.md")

# Clean local __pycache__ folders before packaging to avoid accidental inclusion.
for cache_dir in HERE.rglob("__pycache__"):
    shutil.rmtree(cache_dir, ignore_errors=True)

setup(
    name=PROJECT.get("name", "poly-position-watcher"),
    version=PROJECT.get("version", "0.1.1"),
    description=PROJECT.get("description", ""),
    long_description=README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else "",
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=("tests", "tests.*", "__pycache__")),
    include_package_data=True,
    exclude_package_data={"": ["__pycache__/*", "*.pyc", "*.pyo"]},
    python_requires=PYTHON_REQUIRES,
    install_requires=DEPENDENCIES,
    license=PROJECT.get("license", "MIT"),
    author=PROJECT.get("authors", [{}])[0].get("name", "pinbar"),
    url=PROJECT.get("urls", {}).get("Homepage", "https://github.com/tosmart01/polymarket-position-watcher"),
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
    ],
    project_urls=PROJECT.get("urls", {}),
)
