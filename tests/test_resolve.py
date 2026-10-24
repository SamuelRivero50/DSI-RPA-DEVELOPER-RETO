import pytest
import requests

from cuentas_pipeline.core.models import Causa, Estado
from cuentas_pipeline.steps.resolve import clasificar_excepcion, clasificar_respuesta


class RespuestaFalsa:
    def __init__(self, status_code, datos=None, json_error=None, headers=None):
        self.status_code = status_code
        self._datos = datos
        self._json_error = json_error
        self.headers = headers or {}

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._datos


def test_200_con_id_correcto_es_ok_y_mapea_campos():
    respuesta = RespuestaFalsa(
        200,
        {
            "userId": 3,
            "id": 42,
            "title": "Título",
            "body": "Cuerpo",
        },
    )

    resultado, reintentar = clasificar_respuesta(respuesta, "42")

    assert resultado.estado is Estado.OK
    assert resultado.causa is None
    assert resultado.user_id == 3
    assert resultado.titulo == "Título"
    assert resultado.cuerpo == "Cuerpo"
    assert not reintentar


def test_200_con_id_distinto_es_respuesta_invalida_y_reintenta():
    resultado, reintentar = clasificar_respuesta(RespuestaFalsa(200, {"id": 43}), "42")

    assert resultado.estado is Estado.ERROR_TECNICO
    assert resultado.causa is Causa.RESPUESTA_INVALIDA
    assert reintentar


def test_200_con_json_invalido_es_respuesta_invalida_y_reintenta():
    resultado, reintentar = clasificar_respuesta(
        RespuestaFalsa(200, json_error=ValueError("boom")), "42"
    )

    assert resultado.causa is Causa.RESPUESTA_INVALIDA
    assert reintentar


def test_200_con_json_que_no_es_objeto_es_respuesta_invalida():
    resultado, reintentar = clasificar_respuesta(RespuestaFalsa(200, [42]), "42")

    assert resultado.causa is Causa.RESPUESTA_INVALIDA
    assert reintentar


def test_404_es_no_encontrado_sin_reintento():
    resultado, reintentar = clasificar_respuesta(RespuestaFalsa(404), "0")

    assert resultado.estado is Estado.NO_ENCONTRADO
    assert resultado.causa is Causa.HTTP_404
    assert not reintentar


def test_429_es_error_tecnico_y_reintenta():
    resultado, reintentar = clasificar_respuesta(RespuestaFalsa(429), "42")

    assert resultado.estado is Estado.ERROR_TECNICO
    assert resultado.causa is Causa.HTTP_429
    assert reintentar


@pytest.mark.parametrize("codigo", [500, 503, 599])
def test_5xx_es_error_tecnico_y_reintenta(codigo):
    resultado, reintentar = clasificar_respuesta(RespuestaFalsa(codigo), "42")

    assert resultado.causa is Causa.HTTP_5XX
    assert reintentar


@pytest.mark.parametrize("codigo", [400, 403, 418])
def test_otros_4xx_no_reintentan(codigo):
    resultado, reintentar = clasificar_respuesta(RespuestaFalsa(codigo), "42")

    assert resultado.causa is Causa.HTTP_4XX
    assert not reintentar


def test_timeout_es_error_tecnico_y_reintenta():
    resultado, reintentar = clasificar_excepcion(requests.exceptions.Timeout("tarde"))

    assert resultado.causa is Causa.TIMEOUT
    assert reintentar


def test_connect_timeout_se_clasifica_como_timeout():
    resultado, reintentar = clasificar_excepcion(requests.exceptions.ConnectTimeout("tarde"))

    assert resultado.causa is Causa.TIMEOUT
    assert reintentar


def test_connection_error_es_error_tecnico_y_reintenta():
    resultado, reintentar = clasificar_excepcion(requests.exceptions.ConnectionError("sin red"))

    assert resultado.causa is Causa.CONEXION
    assert reintentar


def test_otra_excepcion_de_requests_no_reintenta():
    resultado, reintentar = clasificar_excepcion(requests.exceptions.RequestException("raro"))

    assert resultado.causa is Causa.ERROR_INESPERADO
    assert not reintentar


def test_excepcion_ajena_a_requests_se_propaga():
    with pytest.raises(ValueError, match="no es de requests"):
        clasificar_excepcion(ValueError("no es de requests"))
