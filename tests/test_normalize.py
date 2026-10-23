from cuentas_pipeline.adapters.csv_reader import leer_csv
from cuentas_pipeline.core.config import EntradaConfig
from cuentas_pipeline.steps.normalize import normalizar


def _normalizar_reto():
    lectura = leer_csv("cuentas.csv", EntradaConfig())
    return normalizar(lectura.filas)


def test_csv_del_reto_produce_los_ids_unicos_esperados():
    resultado = _normalizar_reto()

    assert resultado.lineas_con_datos == 20
    assert resultado.lineas_en_blanco == 1
    assert resultado.repeticiones_ignoradas == 3
    assert len(resultado.filas) == 17
    assert [fila.id for fila in resultado.filas] == [
        "7",
        "12",
        "23",
        "45",
        "99",
        "101",
        "abc",
        "3",
        "58",
        "88",
        "150",
        "64",
        "31",
        "42",
        "76",
        "0",
        "19",
    ]
    assert resultado.repetidos == [("7", 3), ("12", 2)]


def test_conserva_la_primera_aparicion_y_las_apariciones_totales():
    resultado = _normalizar_reto()

    fila7 = next(fila for fila in resultado.filas if fila.id == "7")
    assert fila7.linea_origen == 2
    assert fila7.valor_original == "7"
    assert fila7.apariciones == 3

    fila12 = next(fila for fila in resultado.filas if fila.id == "12")
    assert fila12.linea_origen == 3
    assert fila12.apariciones == 2


def test_limpia_espacios_y_comillas_del_parser():
    resultado = _normalizar_reto()

    fila23 = next(fila for fila in resultado.filas if fila.id == "23")
    assert fila23.valor_original == " 23"
    assert fila23.linea_origen == 4

    fila42 = next(fila for fila in resultado.filas if fila.id == "42")
    assert fila42.valor_original == "42"
    assert fila42.linea_origen == 19


def test_abc_es_dato_invalido_y_no_se_consulta():
    resultado = _normalizar_reto()

    fila = next(fila for fila in resultado.filas if fila.id == "abc")
    assert not fila.valida
    assert fila.linea_origen == 9


def test_normaliza_ceros_a_la_izquierda_y_el_cero_es_valido():
    resultado = normalizar([(2, "007"), (3, "0")])

    assert [fila.id for fila in resultado.filas] == ["7", "0"]
    assert all(fila.valida for fila in resultado.filas)


def test_deduplica_ids_que_quedan_iguales_tras_normalizar():
    resultado = normalizar([(2, "007"), (3, "7")])

    assert len(resultado.filas) == 1
    assert resultado.filas[0].valor_original == "007"
    assert resultado.filas[0].apariciones == 2
    assert resultado.repeticiones_ignoradas == 1


def test_rechaza_formatos_no_enteros():
    resultado = normalizar([(2, "-5"), (3, "3.5"), (4, "１２"), (5, "  abc  ")])

    assert all(not fila.valida for fila in resultado.filas)
    assert [fila.id for fila in resultado.filas] == ["-5", "3.5", "１２", "abc"]
    assert resultado.filas[-1].valor_original == "  abc  "


def test_ignora_y_cuenta_lineas_en_blanco():
    resultado = normalizar([(2, ""), (3, "   "), (4, "7")])

    assert resultado.lineas_en_blanco == 2
    assert resultado.lineas_con_datos == 1
    assert len(resultado.filas) == 1


def test_ordena_por_linea_de_origen():
    resultado = normalizar([(5, "9"), (2, "3")])

    assert [fila.linea_origen for fila in resultado.filas] == [2, 5]


def test_solo_encabezado_no_produce_filas():
    resultado = normalizar([])

    assert resultado.filas == []
    assert resultado.lineas_con_datos == 0
    assert resultado.lineas_en_blanco == 0
    assert resultado.repeticiones_ignoradas == 0
    assert resultado.repetidos == []
