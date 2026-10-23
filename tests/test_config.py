import tomllib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cuentas_pipeline.core.config import (
    ApiConfig,
    Config,
    ConfigInvalidaError,
    ReintentosConfig,
    config_desde_dict,
)


def test_valores_por_defecto():
    config = Config()
    assert config.entrada.archivo == "cuentas.csv"
    assert config.api.url_base == "https://jsonplaceholder.typicode.com/posts"
    assert config.reintentos.max_intentos == 4
    assert config.salida.base_datos == "estado/estado.db"
    assert config.log.nivel == "INFO"


def test_config_toml_del_reto_coincide_con_los_defectos():
    with Path("config.toml").open("rb") as archivo:
        datos = tomllib.load(archivo)
    assert config_desde_dict(datos) == Config()


def test_toml_sobrescribe_solo_lo_indicado():
    config = config_desde_dict(
        {"reintentos": {"max_intentos": 7}, "api": {"timeout_lectura_s": 2.5}}
    )
    assert config.reintentos.max_intentos == 7
    assert config.reintentos.espera_base_s == 1.0
    assert config.api.timeout_lectura_s == 2.5


def test_config_es_inmutable():
    config = Config()
    with pytest.raises(FrozenInstanceError):
        config.api = ApiConfig()


def test_rechaza_max_intentos_menor_que_uno():
    with pytest.raises(ConfigInvalidaError, match=r"\[reintentos\] max_intentos"):
        config_desde_dict({"reintentos": {"max_intentos": 0}})


def test_rechaza_timeout_no_positivo():
    with pytest.raises(ConfigInvalidaError, match="timeout_conexion_s"):
        config_desde_dict({"api": {"timeout_conexion_s": 0}})


def test_rechaza_tipos_incorrectos():
    with pytest.raises(ConfigInvalidaError, match="max_intentos debe ser un entero"):
        config_desde_dict({"reintentos": {"max_intentos": "4"}})


def test_rechaza_booleanos_como_numeros():
    with pytest.raises(ConfigInvalidaError, match="debe ser un entero"):
        config_desde_dict({"reintentos": {"max_intentos": True}})


def test_rechaza_claves_desconocidas():
    with pytest.raises(ConfigInvalidaError, match="claves desconocidas: inventada"):
        config_desde_dict({"api": {"inventada": 1}})


def test_rechaza_nivel_de_log_invalido():
    with pytest.raises(ConfigInvalidaError, match="nivel inválido"):
        config_desde_dict({"log": {"nivel": "VERBOSE"}})


def test_rechaza_codificacion_desconocida():
    with pytest.raises(ConfigInvalidaError, match="codificacion desconocida"):
        config_desde_dict({"entrada": {"codificacion": "no-existe"}})


def test_acepta_entero_en_campo_decimal():
    config = config_desde_dict({"reintentos": {"espera_base_s": 1}})
    assert isinstance(config.reintentos, ReintentosConfig)
    assert config.reintentos.espera_base_s == 1
