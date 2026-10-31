"""Load settings from the project's .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Locate the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")


def get_env(
    name: str,
    required: bool = True,
    default: str | None = None,
) -> str | None:
    """Return an environment variable or raise an error if required."""
    value = os.getenv(name, default)

    if required and not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )

    return value
