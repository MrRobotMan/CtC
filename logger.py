import logging
import os


error_handler = logging.FileHandler("ctc.log", encoding="utf8")
error_handler.setLevel(logging.ERROR)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
error_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
LOGGER = logging.getLogger("ctc")
LOGGER.setLevel(logging.INFO)
LOGGER.addHandler(error_handler)
LOGGER.addHandler(stream_handler)

DEBUG = os.environ.get("CTC_DEBUG", None)
if DEBUG == "Debug":
    LOGGER.setLevel(logging.DEBUG)
