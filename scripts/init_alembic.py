#!/usr/bin/env python
"""Initialize Alembic migrations directory structure."""

import os
import sys

# Ensure alembic directory structure exists
os.makedirs("alembic/versions", exist_ok=True)

# Create __init__.py files
for path in ["alembic", "alembic/versions"]:
    init_file = os.path.join(path, "__init__.py")
    if not os.path.exists(init_file):
        open(init_file, "w").close()
        print(f"Created {init_file}")

print("Alembic directory structure initialized")
