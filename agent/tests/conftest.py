"""Shared test helpers."""

from __future__ import annotations

import os

# Force a temp state dir so tests don't touch the real ~/.homepod-agent.
os.environ.setdefault("HOME_POD_AGENT_STATE_DIR", "/tmp/homepod-agent-tests")