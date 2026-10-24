from datetime import datetime

from cuentas_pipeline.adapters.repository import Repositorio
from cuentas_pipeline.core.config import SalidaConfig
from cuentas_pipeline.core.models import Causa, Estado, FilaCuenta, Resultado


def _repositorio(tmp_path):
    config = SalidaConfig(base_datos=str(tmp_path / "estado.db"))
    return Repositorio(config)


def _fila(linea, valor, id_cuenta, valida=True):
    return FilaCuenta(linea_origen=linea, valor_original=valor, id=id_cuenta, valida=valida)


def test_guardar_ok_persiste_campos_y_conteos(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas("a" * 64, "cuentas.csv", [_fila(2, "7", "7")])

    repo.guardar(
        "a" * 64,
        "7",
        Resultado(
            estado=Estado.OK,
            user_id=1,
            titulo="titulo",
            cuerpo="cuerpo",
            intentos=2,
        ),
    )

    filas = repo.filas("a" * 64)
    assert len(filas) == 1
    assert filas[0]["estado"] == "OK"
    assert filas[0]["causa"] is None
    assert filas[0]["user_id"] == 1
    assert filas[0]["titulo"] == "titulo"
    assert filas[0]["cuerpo"] == "cuerpo"
    assert filas[0]["intentos"] == 2
    assert filas[0]["detalle_error"] is None
    assert repo.conteos("a" * 64) == {Estado.OK: 1}
    repo.cerrar()


def test_guardar_no_encontrado_con_causa(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas("a" * 64, "cuentas.csv", [_fila(2, "101", "101")])

    repo.guardar(
        "a" * 64,
        "101",
        Resultado(estado=Estado.NO_ENCONTRADO, causa=Causa.HTTP_404, intentos=1),
    )

    fila = repo.filas("a" * 64)[0]
    assert fila["estado"] == "NO_ENCONTRADO"
    assert fila["causa"] == "HTTP_404"
    assert repo.conteos("a" * 64) == {Estado.NO_ENCONTRADO: 1}
    repo.cerrar()


def test_guardar_error_tecnico_con_detalle(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas("a" * 64, "cuentas.csv", [_fila(2, "7", "7")])

    repo.guardar(
        "a" * 64,
        "7",
        Resultado(
            estado=Estado.ERROR_TECNICO,
            causa=Causa.TIMEOUT,
            intentos=4,
            detalle_error="tarde",
        ),
    )

    fila = repo.filas("a" * 64)[0]
    assert fila["estado"] == "ERROR_TECNICO"
    assert fila["causa"] == "TIMEOUT"
    assert fila["intentos"] == 4
    assert fila["detalle_error"] == "tarde"
    repo.cerrar()


def test_las_invalidas_cuentan_como_dato_invalido(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas("a" * 64, "cuentas.csv", [_fila(9, "abc", "abc", valida=False)])

    fila = repo.filas("a" * 64)[0]
    assert fila["estado"] == "DATO_INVALIDO"
    assert fila["causa"] == "FORMATO_INVALIDO"
    assert fila["intentos"] == 0
    assert repo.conteos("a" * 64) == {Estado.DATO_INVALIDO: 1}
    repo.cerrar()


def test_filas_ordenadas_y_conteos_de_varios_estados(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas(
        "a" * 64,
        "cuentas.csv",
        [_fila(5, "8", "8"), _fila(2, "7", "7"), _fila(9, "abc", "abc", valida=False)],
    )
    repo.guardar("a" * 64, "7", Resultado(estado=Estado.OK, intentos=1))
    repo.guardar(
        "a" * 64, "8", Resultado(estado=Estado.ERROR_TECNICO, causa=Causa.CONEXION, intentos=2)
    )

    filas = repo.filas("a" * 64)

    assert [fila["id"] for fila in filas] == ["7", "8", "abc"]
    assert repo.conteos("a" * 64) == {
        Estado.OK: 1,
        Estado.ERROR_TECNICO: 1,
        Estado.DATO_INVALIDO: 1,
    }
    repo.cerrar()


def test_las_marcas_de_tiempo_son_iso_con_zona(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas("a" * 64, "cuentas.csv", [_fila(2, "7", "7")])
    repo.guardar("a" * 64, "7", Resultado(estado=Estado.OK, intentos=1))

    fila = repo.filas("a" * 64)[0]

    assert datetime.fromisoformat(fila["creado_en"]).tzinfo is not None
    assert datetime.fromisoformat(fila["actualizado_en"]).tzinfo is not None
    repo.cerrar()


def test_los_datos_persisten_al_reabrir(tmp_path):
    config = SalidaConfig(base_datos=str(tmp_path / "estado.db"))
    repo = Repositorio(config)
    repo.cargar_filas("a" * 64, "cuentas.csv", [_fila(2, "7", "7")])
    repo.guardar("a" * 64, "7", Resultado(estado=Estado.OK, intentos=1))
    repo.cerrar()

    repo = Repositorio(config)

    assert repo.conteos("a" * 64) == {Estado.OK: 1}
    assert repo.pendientes("a" * 64) == []
    repo.cerrar()


def test_guardar_no_afecta_a_otro_hash(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas("a" * 64, "cuentas.csv", [_fila(2, "7", "7")])
    repo.cargar_filas("b" * 64, "cuentas.csv", [_fila(2, "7", "7")])

    repo.guardar("a" * 64, "7", Resultado(estado=Estado.OK, intentos=1))

    assert repo.conteos("b" * 64) == {Estado.PENDIENTE: 1}
    repo.cerrar()
