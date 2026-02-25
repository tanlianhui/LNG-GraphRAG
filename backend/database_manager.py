"""Backend database manager facade.

Keeps backend imports stable while core implementation remains in root-level
`database_manager.py` for backward compatibility with existing scripts.
"""

from database_manager import *  # noqa: F401,F403

