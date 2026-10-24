from cuentas_pipeline.adapters.repository import Repositorio
from cuentas_pipeline.core.config import SalidaConfig
from cuentas_pipeline.core.models import FilaCuenta


def _repositorio(tmp_path):
    config = SalidaConfig(base_datos=str(tmp_path / "estado" / "estado.db"))
    return Repositorio(config)


def _fila(linea, valor, id_cuenta, apariciones=1, valida=True):
    return FilaCuenta(
        linea_origen=linea,
        valor_original=valor,
        id=id_cuenta,
        apariciones=apariciones,
        valida=valida,
    )


def test_las_validas_quedan_pendientes_por_orden_de_linea(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas(
        "a" * 64,
        "cuentas.csv",
        [_fila(4, " 23", "23"), _fila(2, "7", "7", apariciones=3)],
    )

    pendientes = repo.pendientes("a" * 64)

    assert [fila.id for fila in pendientes] == ["7", "23"]
    assert pendientes[0].apariciones == 3
    assert pendientes[0].valor_original == "7"
    repo.cerrar()


def test_las_invalidas_no_se_consultan(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas("a" * 64, "cuentas.csv", [_fila(9, "abc", "abc", valida=False)])

    assert repo.pendientes("a" * 64) == []
    repo.cerrar()


def test_insert_or_ignore_no_duplica_ni_pisa_la_primera_carga(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas("a" * 64, "cuentas.csv", [_fila(2, "7", "7")])
    repo.cargar_filas("a" * 64, "otro.csv", [_fila(8, " 7 ", "7", apariciones=2)])

    pendientes = repo.pendientes("a" * 64)

    assert len(pendientes) == 1
    assert pendientes[0].linea_origen == 2
    assert pendientes[0].valor_original == "7"
    assert pendientes[0].apariciones == 1
    repo.cerrar()


def test_separa_los_pendientes_por_hash(tmp_path):
    repo = _repositorio(tmp_path)
    repo.cargar_filas("a" * 64, "cuentas.csv", [_fila(2, "7", "7")])
    repo.cargar_filas("b" * 64, "cuentas.csv", [_fila(2, "8", "8")])

    assert [fila.id for fila in repo.pendientes("a" * 64)] == ["7"]
    assert [fila.id for fila in repo.pendientes("b" * 64)] == ["8"]
    repo.cerrar()


def test_crea_la_carpeta_de_la_base(tmp_path):
    ruta = tmp_path / "nueva" / "carpeta" / "estado.db"
    repo = Repositorio(SalidaConfig(base_datos=str(ruta)))

    assert ruta.exists()
    repo.cerrar()
