"""Create a new Memory store."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.config import load_config
from harness.memory_store.builder import MemoryStoreBuilder
from harness.telemetry import setup_telemetry       


def main() -> None:
    config = load_config()
    setup_telemetry(config)
    store_builder = MemoryStoreBuilder(config, "agent-memory-store")
    store_builder.create_if_not_exist()


if __name__ == "__main__":
    main()
