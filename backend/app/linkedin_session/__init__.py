"""Server-side Playwright sessions for LinkedIn accounts."""
from .service import get_manager, shutdown_manager

__all__ = ["get_manager", "shutdown_manager"]
