"""Backend auth DB facade.

Keeps backend imports stable while core implementation remains in root-level
`auth_db.py` for backward compatibility with existing scripts.
"""

from auth_db import *  # noqa: F401,F403

