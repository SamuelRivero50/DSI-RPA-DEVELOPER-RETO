import argparse
import logging
import time
import tomllib
from dataclasses import replace

from cuentas_pipeline.adapters.api_client import ApiClient
from cuentas_pipeline.adapters.csv_reader import leer_csv
from cuentas_pipeline.adapters.excel_writer import ExcelWriter
from cuentas_pipeline.adapters.repository import Repositorio
from cuentas_pipeline.core.config import ConfigInvalidaError, config_desde_dict
from cuentas_pipeline.core.models import Estado, ResumenEjecucion
from cuentas_pipeline.logging_setup import configurar_logging
from cuentas_pipeline.pipeline import ejecutar

logger = logging.getLogger(__name__)


def _cargar_config(ruta: str, archivo_entrada: str | None):
    try:
        with open(ruta, "rb") as archivo:
            datos = tomllib.load(archivo)
    except OSError as error:
        raise ConfigInvalidaError(f"no se pudo leer la configuración {ruta}: {error}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigInvalidaError(f"configuración TOML inválida {ruta}: {error}") from error

    config = config_desde_dict(datos)
    if archivo_entrada is not None:
        config = replace(config, entrada=replace(config.entrada, archivo=archivo_entrada))
    return config


def codigo_salida(resumen: ResumenEjecucion) -> int:
    pendientes = resumen.por_estado.get(Estado.PENDIENTE, 0)
    errores = resumen.por_estado.get(Estado.ERROR_TECNICO, 0)
    return 1 if pendientes or errores else 0


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Consolida el CSV diario de cuentas médicas contra la API."
    )
    parser.add_argument("--input", dest="archivo_entrada", help="ruta del CSV de entrada")
    parser.add_argument("--config", default="config.toml", help="ruta del TOML de configuración")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _construir_parser().parse_args(argv)

    try:
        config = _cargar_config(args.config, args.archivo_entrada)
        configurar_logging(config.log)
        logger.info(
            "config entrada=%s api=%s reintentos=%s salida=%s log=%s",
            config.entrada,
            config.api,
            config.reintentos,
            config.salida,
            config.log,
        )

        lectura = leer_csv(config.entrada.archivo, config.entrada)
        repo = Repositorio(config.salida)
        try:
            cliente = ApiClient(config.api)
            try:
                escritor = ExcelWriter(config.salida)
                resumen = ejecutar(
                    lectura, config, repo, cliente, escritor=escritor, sleep=time.sleep
                )
            finally:
                cliente.cerrar()
        finally:
            repo.cerrar()

        codigo = codigo_salida(resumen)
        logger.info(
            "estado=%s codigo_salida=%d",
            {estado.value: total for estado, total in resumen.por_estado.items()},
            codigo,
        )
        return codigo
    except Exception:
        logger.exception("error fatal")
        return 2
