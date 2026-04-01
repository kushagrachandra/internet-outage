import logging
import sys

from outage_monitor.main import main

if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
        logging.error("%s", e)
        sys.exit(1)
