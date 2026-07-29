"""Evaluation datasets and runners for Innova AI."""

import os
import tempfile


os.environ["DEEPEVAL_DISABLE_DOTENV"] = "1"
os.environ["CONFIDENT_API_KEY"] = ""
os.environ.setdefault("DEEPEVAL_NO_INSPECT_PROMPT", "1")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault(
    "DEEPEVAL_CACHE_FOLDER",
    os.path.join(tempfile.gettempdir(), "innova-deepeval-cache"),
)
