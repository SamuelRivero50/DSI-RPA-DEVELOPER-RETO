import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from cuentas_pipeline.core.config import LogConfig

_FORMATO = "%(asctime)s %(levelname)s %(module)s %(message)s"


def configurar_logging(config: LogConfig) -> None:
    ruta = Path(config.archivo)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    raiz = logging.getLogger()
    raiz.setLevel(config.nivel)
    for handler in raiz.handlers[:]:
        raiz.removeHandler(handler)
        handler.close()

    formato = logging.Formatter(_FORMATO)

    archivo = RotatingFileHandler(
        ruta,
        maxBytes=config.max_bytes,
        backupCount=config.copias,
        encoding="utf-8",
    )
    archivo.setFormatter(formato)
    raiz.addHandler(archivo)

    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    raiz.addHandler(consola)
