import requests

from cuentas_pipeline.core.models import Causa, Estado, Resultado


def _error(causa: Causa, detalle: str, reintentar: bool) -> tuple[Resultado, bool]:
    return Resultado(estado=Estado.ERROR_TECNICO, causa=causa, detalle_error=detalle), reintentar


def _id_coincide(recibido: object, esperado: str) -> bool:
    try:
        return recibido == int(esperado)
    except (TypeError, ValueError):
        return False


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

    return _error(Causa.HTTP_4XX, f"HTTP inesperado {estado_http}", False)


def clasificar_excepcion(error: Exception) -> tuple[Resultado, bool]:
    if isinstance(error, requests.exceptions.Timeout):
        return _error(Causa.TIMEOUT, str(error), True)

    if isinstance(error, requests.exceptions.ConnectionError):
        return _error(Causa.CONEXION, str(error), True)

    if isinstance(error, requests.exceptions.RequestException):
        return _error(Causa.ERROR_INESPERADO, str(error), False)

    raise error
