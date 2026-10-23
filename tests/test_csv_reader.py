from hashlib import sha256

import pytest

from cuentas_pipeline.adapters.csv_reader import ErrorEntrada, leer_csv
from cuentas_pipeline.core.config import EntradaConfig


def test_lee_el_csv_del_reto_sin_tocarlo():
    lectura = leer_csv("cuentas.csv", EntradaConfig())
    contenido = open("cuentas.csv", "rb").read()

    assert lectura.nombre == "cuentas.csv"
    assert lectura.archivo_hash == sha256(contenido).hexdigest()
    assert lectura.hash8 == lectura.archivo_hash[:8]
    assert len(lectura.filas) == 21
    assert lectura.filas[0] == (2, "7")
    assert lectura.filas[2] == (4, " 23")
    assert lectura.filas[10] == (12, "")
    assert lectura.filas[17] == (19, "42")


def test_encuentra_la_columna_aunque_el_encabezado_tenga_espacios(tmp_path):
    ruta = tmp_path / "cuentas.csv"
    ruta.write_text(" otro, id_cuenta \nx,42\n", encoding="utf-8")

    lectura = leer_csv(ruta, EntradaConfig())

    assert lectura.filas == [(2, "42")]


def test_fallo_si_no_existe(tmp_path):
    with pytest.raises(ErrorEntrada, match="no se pudo leer"):
        leer_csv(tmp_path / "no-existe.csv", EntradaConfig())


def test_fallo_si_no_decodifica(tmp_path):
    ruta = tmp_path / "cuentas.csv"
    ruta.write_bytes(b"id_cuenta\n\xff\xfe\n")

    with pytest.raises(ErrorEntrada, match="no se puede decodificar"):
        leer_csv(ruta, EntradaConfig())


def test_fallo_si_falta_la_columna(tmp_path):
    ruta = tmp_path / "cuentas.csv"
    ruta.write_text("cuenta\n42\n", encoding="utf-8")

    with pytest.raises(ErrorEntrada, match="no contiene la columna id_cuenta"):
        leer_csv(ruta, EntradaConfig())


def test_fallo_si_el_archivo_esta_vacio(tmp_path):
    ruta = tmp_path / "cuentas.csv"
    ruta.write_bytes(b"")

    with pytest.raises(ErrorEntrada, match="está vacío"):
        leer_csv(ruta, EntradaConfig())


def test_fila_con_menos_columnas_devuelve_vacio(tmp_path):
    ruta = tmp_path / "cuentas.csv"
    ruta.write_text("id_cuenta\n\n7\n", encoding="utf-8")

    lectura = leer_csv(ruta, EntradaConfig())

    assert lectura.filas == [(2, ""), (3, "7")]
