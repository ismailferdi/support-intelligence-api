from logging import getLogger, StreamHandler, Formatter
import sys


logger = getLogger("support_api")

handler = StreamHandler(sys.stdout)
formater = Formatter("%(asctime)s | %(levelname)s | %(message)s")
handler.setFormatter(formater)

logger.addHandler(handler)