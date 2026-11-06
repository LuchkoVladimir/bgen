"""bgen_lib: публичный API библиотеки bgen."""
from .common import BgenError
from .build import build
from .project import stat

__all__ = ["BgenError", "build", "stat"]
