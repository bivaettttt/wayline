import logging
import os
from time import sleep

from wayline.integration import sync

logging.basicConfig(level=logging.INFO)

while True:
    try:
        sync()
    except Exception:
        logging.exception("Poll rolled back. Next cycle will retry the checkpoint")
    sleep(600 if os.getenv("LAB_MODE") == "1" else 8)
