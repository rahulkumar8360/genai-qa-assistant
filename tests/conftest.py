# Shared test setup.
#
# The suite must never call the real API: it has to run in a second, on any
# machine, with or without a key. Forcing the offline backend here - before
# config is imported anywhere - guarantees that even if ANTHROPIC_API_KEY is set.

import os
import sys

os.environ["QA_BACKEND"] = "offline"
os.environ["QA_PROMPT_VERSION"] = "v3"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
