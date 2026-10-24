import logging
import math
import random
import time
from dataclasses import replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import requests

from cuentas_pipeline.core.config import ReintentosConfig
from cuentas_pipeline.core.models import Causa, Estado, Resultado

logger = logging.getLogger(__name__)


def _error(causa: Causa, detalle: str, reintentar: bool) -> tuple[Resultado, bool]:
    return Resultado(estado=Estado.ERROR_TECNICO, causa=causa, detalle_error=detalle), reintentar


def _id_coincide(recibido: object, esperado: str) -> bool:
    try:
        return recibido == int(esperado)
    except (TypeError, ValueError):
        return False


def _detalle_log(valor: str | None) -> str:
    if not valor:
        return "-"
    return " ".join(str(valor).split())[:300]


def clasificar_respuesta(respuesta: requests.Response, id_esperado: str) -> tuple[Resultado, bool]:
    estado_http = respuesta.status_code

    if estado_http == 404:
        resultado = Resultado(
            estado=Estado.NO_ENCONTRADO,
            causa=Causa.HTTP_404,
            detalle_error="HTTP 404",
        )
        return resultado, False

    if estado_http == 429:
        return _error(Causa.HTTP_429, "HTTP 429", True)

    if 500 <= estado_http < 600:
        return _error(Causa.HTTP_5XX, f"HTTP {estado_http}", True)

    if estado_http == 200:
        try:
            datos = respuesta.json()
        except ValueError:
            return _error(Causa.RESPUESTA_INVALIDA, "JSON inválido", True)

        if not isinstance(datos, dict):
            return _error(Causa.RESPUESTA_INVALIDA, "el JSON no es un objeto", True)

        if not _id_coincide(datos.get("id"), id_esperado):
            return _error(
                Causa.RESPUESTA_INVALIDA,
                f"id esperado={id_esperado} recibido={datos.get('id')}",
                True,
            )

        resultado = Resultado(
            estado=Estado.OK,
            user_id=datos.get("userId"),
            titulo=datos.get("title"),
            cuerpo=datos.get("body"),
        )
        return resultado, False

    if 400 <= estado_http < 500:
        return _error(Causa.HTTP_4XX, f"HTTP {estado_http}", False)

    return _error(Causa.ERROR_INESPERADO, f"HTTP inesperado {estado_http}", False)


def clasificar_excepcion(error: Exception) -> tuple[Resultado, bool]:
    if isinstance(error, requests.exceptions.Timeout):
        return _error(Causa.TIMEOUT, str(error), True)

    if isinstance(error, requests.exceptions.ConnectionError):
        return _error(Causa.CONEXION, str(error), True)

    if isinstance(error, requests.exceptions.RequestException):
        return _error(Causa.ERROR_INESPERADO, str(error), False)

    raise error


def _espera(intento: int, config: ReintentosConfig, uniform) -> float:
    tope = min(config.espera_maxima_s, config.espera_base_s * config.factor ** (intento - 1))
    return tope / 2 + uniform(0, tope / 2)


def _retry_after(respuesta, config: ReintentosConfig) -> float | None:
    valor = respuesta.headers.get("Retry-After") or respuesta.headers.get("retry-after")
    if valor is None:
        return None

    texto = valor.strip()
    try:
        segundos = float(texto)
    except ValueError:
        try:
            fecha = parsedate_to_datetime(texto)
        except (TypeError, ValueError):
            return None
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=UTC)
        segundos = (fecha - datetime.now(UTC)).total_seconds()

    if not math.isfinite(segundos) or segundos < 0:
        return None
    return min(segundos, config.retry_after_maximo_s)


def resolver(
    cliente,
    id_cuenta: str,
    config: ReintentosConfig,
    sleep=time.sleep,
    uniform=random.uniform,
) -> Resultado:
    for intento in range(1, config.max_intentos + 1):
        retry_after = None
        inicio_peticion = time.monotonic()
        try:
            respuesta = cliente.obtener(id_cuenta)
        except requests.exceptions.RequestException as error:
            resultado, reintentar = clasificar_excepcion(error)
            estado_http = None
        else:
            estado_http = respuesta.status_code
            resultado, reintentar = clasificar_respuesta(respuesta, id_cuenta)
            if reintentar:
                retry_after = _retry_after(respuesta, config)

        duracion_ms = (time.monotonic() - inicio_peticion) * 1000
        hay_siguiente = reintentar and intento < config.max_intentos
        espera = 0.0
        if hay_siguiente:
            espera = _espera(intento, config, uniform)
            if retry_after is not None:
                espera = retry_after

        detalle = _detalle_log(resultado.detalle_error)
        logger.info(
            "peticion id=%s intento=%d/%d http=%s estado=%s causa=%s "
            "detalle=%s espera=%.2f duracion_ms=%.0f",
            id_cuenta,
            intento,
            config.max_intentos,
            estado_http if estado_http is not None else "-",
            resultado.estado.value,
            resultado.causa.value if resultado.causa is not None else "-",
            detalle,
            espera,
            duracion_ms,
        )

        if resultado.estado is Estado.ERROR_TECNICO:
            logger.warning(
                "intento fallido id=%s intento=%d/%d causa=%s detalle=%s espera=%.2f",
                id_cuenta,
                intento,
                config.max_intentos,
                resultado.causa,
                detalle,
                espera,
            )

        if not hay_siguiente:
            return replace(resultado, intentos=intento)

        sleep(espera)

    raise AssertionError("el bucle de reintentos no terminó")
