import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import homecam2_side  # noqa: E402
import homecam2_top  # noqa: E402


def _run_module(module) -> None:
    module.main()


def main() -> None:
    print("Starting side camera script...")
    side_thread = threading.Thread(target=_run_module, args=(homecam2_side,), daemon=False)

    print("Starting top camera script...")
    top_thread = threading.Thread(target=_run_module, args=(homecam2_top,), daemon=False)

    side_thread.start()
    top_thread.start()

    try:
        side_thread.join()
        top_thread.join()
    except KeyboardInterrupt:
        print("Stopping both camera runs...")


if __name__ == "__main__":
    main()
