import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = tempfile.mkdtemp(prefix="opsboard-test-")
os.environ["OPS_DATA_DIR"] = DATA
os.environ["OPS_SECRET_STORE"] = "file"
for key in ("OPS_CONFIG", "OPS_NOTES", "OPS_TOKEN_FILE", "OPS_HIS_ROOT", "OPS_PORT"):
    os.environ.pop(key, None)
sys.path.insert(0, str(ROOT))
