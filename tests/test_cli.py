import logging
from pathlib import Path

import pytest

from cuentas_pipeline.cli import _cargar_config, codigo_salida, main
from cuentas_pipeline.core.config import ConfigInvalidaError
from cuentas_pipeline.core.models import Estado, ResumenEjecucion


def _resumen(**estados):
    por_estado = {estado: 0 for estado in Estado}
    por_estado.update(estados)
    return ResumenEjecucion(
        archivo_nombre="cuentas.csv",
        archivo_hash="a" * 64,
        lineas_con_datos=0,
        lineas_en_blanco=0,
        repeticiones_ignoradas=0,
        ids_unicos=0,
        por_estado=por_estado,
    )


def test_codigo_cero_si_no_queda_nada_por_resolver():
    assert codigo_salida(_resumen()) == 0
    assert codigo_salida(_resumen(**{Estado.OK: 3, Estado.NO_ENCONTRADO: 1})) == 0
    assert codigo_salida(_resumen(**{Estado.DATO_INVALIDO: 1})) == 0


def test_codigo_uno_si_quedan_errores_tecnicos_o_pendientes():
    assert codigo_salida(_resumen(**{Estado.OK: 1, Estado.ERROR_TECNICO: 1})) == 1
    assert codigo_salida(_resumen(**{Estado.PENDIENTE: 1})) == 1


def test_carga_el_toml_del_reto():
    config = _cargar_config("config.toml", None)

    assert config.entrada.archivo == "cuentas.csv"
    assert config.reintentos.max_intentos == 4


def test_input_sobrescribe_la_ruta_del_toml():
    config = _cargar_config("config.toml", "otro.csv")

    assert config.entrada.archivo == "otro.csv"
    assert config.entrada.columna == "id_cuenta"


def test_config_inexistente_falla_con_mensaje_claro(tmp_path):
    with pytest.raises(ConfigInvalidaError, match="no se pudo leer la configuración"):
        _cargar_config(str(tmp_path / "no.toml"), None)


def test_toml_invalido_falla_con_mensaje_claro(tmp_path):
    ruta = tmp_path / "malo.toml"
    ruta.write_text("[entrada\n", encoding="utf-8")

    with pytest.raises(ConfigInvalidaError, match="TOML inválida"):
        _cargar_config(str(ruta), None)


def test_main_sale_con_dos_si_no_puede_leer_la_configuracion(tmp_path, monkeypatch):
    raiz = logging.getLogger()
    handlers_previos = raiz.handlers[:]
    nivel_previo = raiz.level
    try:
        monkeypatch.chdir(tmp_path)
        codigo = main(["--config", str(tmp_path / "no.toml")])

        assert codigo == 2
        texto = (tmp_path / "logs" / "proceso.log").read_text(encoding="utf-8")
        assert "error fatal" in texto
        assert "FileNotFoundError" in texto
    finally:
        for handler in raiz.handlers[:]:
            raiz.removeHandler(handler)
            handler.close()
        for handler in handlers_previos:
            raiz.addHandler(handler)
        raiz.setLevel(nivel_previo)


def test_el_modulo_se_puede_ejecutar():
    assert Path("src/cuentas_pipeline/__main__.py").exists()
