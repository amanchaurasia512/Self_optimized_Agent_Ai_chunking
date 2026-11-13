"""Project folders in one place. New code imports these; existing scripts keep their own paths."""
from src.common.manifest import PROJECT_ROOT, RUNS_DIR

DATA = PROJECT_ROOT / "data"
EXTRACTED = DATA / "extracted"
CHUNKS = DATA / "chunks"
GOLD = DATA / "gold"
RESULTS = DATA / "results"
EMBEDDINGS = DATA / "embeddings"
RUNS = RUNS_DIR
AGENT_CACHE = DATA / "agent_cache"
