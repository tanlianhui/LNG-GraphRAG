# Backend Layer

This package provides a structured backend import path:

- `backend.web_app` -> Flask app entrypoint
- `backend.auth_db` -> auth/database functions
- `backend.database_manager` -> pipeline DB manager

Existing root-level modules are kept for backward compatibility, while launchers
and internal imports now prefer `backend.*`.

