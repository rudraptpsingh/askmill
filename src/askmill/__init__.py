"""AskMill local inference API."""

from importlib.metadata import PackageNotFoundError, version

from .contract import Batch, GenerationSettings, Profile, Request, Result

__all__ = ["GenerationSettings", "Batch", "Profile", "Request", "Result"]

try:
    __version__ = version("askmill")
except PackageNotFoundError:
    __version__ = "uninstalled"
