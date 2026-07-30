import os
import shutil
import tempfile
from pathlib import Path
import pytest
import contextlib

# Find project root relative to tests directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Create a temporary directory for tests
test_dir = tempfile.mkdtemp(prefix="raphael_test_")

# Set the environment overrides BEFORE importing config or paths
os.environ["RAPHAEL_CONFIG_DIR"] = os.path.join(test_dir, "config")
os.environ["RAPHAEL_DATA_DIR"] = os.path.join(test_dir, "data")
os.environ["RAPHAEL_ROAMING_DIR"] = os.path.join(test_dir, "roaming")

# Create structures
Path(os.environ["RAPHAEL_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["RAPHAEL_DATA_DIR"]).mkdir(parents=True, exist_ok=True)
roaming_mem = Path(os.environ["RAPHAEL_ROAMING_DIR"]) / "memory"
roaming_mem.mkdir(parents=True, exist_ok=True)
Path(os.environ["RAPHAEL_ROAMING_DIR"]).joinpath("goals").mkdir(parents=True, exist_ok=True)
Path(os.environ["RAPHAEL_ROAMING_DIR"]).joinpath("logs").mkdir(parents=True, exist_ok=True)

# Copy seed files from repo memory directory to test memory directory
src_mem = PROJECT_ROOT / "memory"
if src_mem.exists():
    for f in ["long_term.json", "agent_evolution.json"]:
        src_file = src_mem / f
        if src_file.exists():
            shutil.copy(src_file, roaming_mem / f)


@pytest.fixture(scope="session", autouse=True)
def cleanup_temp_dir():
    yield
    # Clean up the directory after tests
    with contextlib.suppress(Exception):
        shutil.rmtree(test_dir)
