import logging
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest
import requests

from cuentas_pipeline.core.config import ReintentosConfig
from cuentas_pipeline.core.models import Causa, Estado
from cuentas_pipeline.steps.resolve import clasificar_excepcion, clasificar_respuesta, resolver


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


class ClienteFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def obtener(self, id_cuenta):
        self.llamadas.append(id_cuenta)
        valor = self.respuestas.pop(0)
        if isinstance(valor, Exception):
            raise valor
        return valor


def _resolver(cliente, config=None, esperas=None):
    esperas = esperas if esperas is not None else []
    resultado = resolver(
        cliente,
        "42",
        config or ReintentosConfig(),
        sleep=esperas.append,
        uniform=lambda _minimo, maximo: maximo,
    )
    return resultado, esperas


def test_404_se_resuelve_en_un_solo_intento():
    cliente = ClienteFalso([RespuestaFalsa(404)])

    resultado, esperas = _resolver(cliente)

    assert resultado.estado is Estado.NO_ENCONTRADO
    assert resultado.intentos == 1
    assert len(cliente.llamadas) == 1
    assert esperas == []


def test_500_seguido_de_200_termina_en_ok():
    cliente = ClienteFalso([RespuestaFalsa(500), RespuestaFalsa(200, {"id": 42})])

    resultado, esperas = _resolver(cliente)

    assert resultado.estado is Estado.OK
    assert resultado.intentos == 2
    assert len(cliente.llamadas) == 2
    assert esperas == [1.0]


def test_timeout_seguido_de_200_termina_en_ok():
    cliente = ClienteFalso([requests.exceptions.Timeout("tarde"), RespuestaFalsa(200, {"id": 42})])

    resultado, esperas = _resolver(cliente)

    assert resultado.estado is Estado.OK
    assert resultado.intentos == 2
    assert esperas == [1.0]


def test_429_respeta_retry_after_en_segundos():
    cliente = ClienteFalso(
        [RespuestaFalsa(429, headers={"Retry-After": "7"}), RespuestaFalsa(200, {"id": 42})]
    )

    resultado, esperas = _resolver(cliente)

    assert resultado.estado is Estado.OK
    assert esperas == [7.0]


def test_retry_after_se_limita_al_maximo():
    cliente = ClienteFalso(
        [RespuestaFalsa(429, headers={"Retry-After": "120"}), RespuestaFalsa(200, {"id": 42})]
    )

    resultado, esperas = _resolver(cliente, ReintentosConfig(retry_after_maximo_s=60.0))

    assert resultado.estado is Estado.OK
    assert esperas == [60.0]


def test_retry_after_acepta_fecha_http():
    fecha = format_datetime(
        datetime.now(UTC) + timedelta(seconds=10), usegmt=True
    )
    cliente = ClienteFalso(
        [RespuestaFalsa(429, headers={"Retry-After": fecha}), RespuestaFalsa(200, {"id": 42})]
    )

    resultado, esperas = _resolver(cliente)

    assert resultado.estado is Estado.OK
    assert 8.0 <= esperas[0] <= 10.0


def test_retry_after_invalido_usa_la_espera_exponencial():
    cliente = ClienteFalso(
        [RespuestaFalsa(429, headers={"Retry-After": "luego"}), RespuestaFalsa(200, {"id": 42})]
    )

    resultado, esperas = _resolver(cliente)

    assert resultado.estado is Estado.OK
    assert esperas == [1.0]


def test_timeout_repetido_agota_los_intentos():
    cliente = ClienteFalso([requests.exceptions.Timeout("tarde")] * 3)

    resultado, esperas = _resolver(cliente, ReintentosConfig(max_intentos=3))

    assert resultado.estado is Estado.ERROR_TECNICO
    assert resultado.causa is Causa.TIMEOUT
    assert resultado.intentos == 3
    assert len(cliente.llamadas) == 3
    assert esperas == [1.0, 2.0]


def test_la_espera_crece_y_respeta_el_techo():
    cliente = ClienteFalso([RespuestaFalsa(500)] * 5)

    resultado, esperas = _resolver(
        cliente,
        ReintentosConfig(max_intentos=5, espera_base_s=1.0, factor=2.0, espera_maxima_s=3.0),
    )

    assert resultado.estado is Estado.ERROR_TECNICO
    assert resultado.intentos == 5
    assert esperas == [1.0, 2.0, 3.0, 3.0]


def test_no_duerme_despues_del_ultimo_intento():
    cliente = ClienteFalso([RespuestaFalsa(500)] * 2)

    _, esperas = _resolver(cliente, ReintentosConfig(max_intentos=2))

    assert len(esperas) == 1


def test_4xx_no_reintenta_y_cuenta_un_intento():
    cliente = ClienteFalso([RespuestaFalsa(400), RespuestaFalsa(200, {"id": 42})])

    resultado, esperas = _resolver(cliente)

    assert resultado.causa is Causa.HTTP_4XX
    assert resultado.intentos == 1
    assert len(cliente.llamadas) == 1
    assert esperas == []


def test_excepcion_inesperada_del_cliente_se_propaga():
    cliente = ClienteFalso([ValueError("boom")])

    with pytest.raises(ValueError, match="boom"):
        _resolver(cliente)


def test_registra_warning_por_intento_fallido(caplog):
    cliente = ClienteFalso([RespuestaFalsa(500), RespuestaFalsa(200, {"id": 42})])

    with caplog.at_level(logging.WARNING, logger="cuentas_pipeline.steps.resolve"):
        _resolver(cliente)

    assert "id=42" in caplog.text
    assert "intento=1/4" in caplog.text
    assert "causa=HTTP_5XX" in caplog.text
    assert "espera=1.00" in caplog.text
