import logging
import sys

from cuentas_pipeline.core.config import LogConfig
from cuentas_pipeline.logging_setup import configurar_logging


def test_escribe_archivo_de_log_con_formato(tmp_path):
    raiz = logging.getLogger()
    handlers_previos = raiz.handlers[:]
    nivel_previo = raiz.level
    try:
        config = LogConfig(
            archivo=str(tmp_path / "logs" / "proceso.log"),
            nivel="INFO",
            max_bytes=1024,
            copias=1,
        )

        configurar_logging(config)
        logging.getLogger("prueba").info("id=7 estado=OK intentos=1")
        for handler in raiz.handlers:
            handler.flush()

        texto = (tmp_path / "logs" / "proceso.log").read_text(encoding="utf-8")
        assert "INFO" in texto
        assert "test_logging_setup" in texto
        assert "id=7 estado=OK intentos=1" in texto
    finally:
        for handler in raiz.handlers[:]:
            raiz.removeHandler(handler)
            handler.close()
        for handler in handlers_previos:
            raiz.addHandler(handler)
        raiz.setLevel(nivel_previo)


def test_reconfigura_stdout_y_stderr_con_replace(monkeypatch, tmp_path):
    class SalidaFalsa:
        def __init__(self):
            self.errors = "strict"

        def reconfigure(self, **cambios):
            self.errors = cambios["errors"]

    stdout = SalidaFalsa()
    stderr = SalidaFalsa()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    raiz = logging.getLogger()
    handlers_previos = raiz.handlers[:]
    nivel_previo = raiz.level
    try:
        configurar_logging(
            LogConfig(
                archivo=str(tmp_path / "logs" / "proceso.log"),
                nivel="INFO",
            )
        )

        assert stdout.errors == "replace"
        assert stderr.errors == "replace"
    finally:
        for handler in raiz.handlers[:]:
            raiz.removeHandler(handler)
            handler.close()
        for handler in handlers_previos:
            raiz.addHandler(handler)
        raiz.setLevel(nivel_previo)
