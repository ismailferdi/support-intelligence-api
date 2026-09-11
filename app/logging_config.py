from logging import getLogger, StreamHandler, INFO, Formatter
import sys


logger = getLogger("support_api")
logger.setLevel(INFO)

handler = StreamHandler(sys.stdout)
formater = Formatter("%(asctime)s | %(levelname)s | %(message)s")
handler.setFormatter(formater)

logger.addHandler(handler)