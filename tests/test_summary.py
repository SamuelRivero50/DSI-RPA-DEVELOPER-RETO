import re
from pathlib import Path

from cuentas_pipeline.core.models import Causa, Estado, ResumenEjecucion
from cuentas_pipeline.steps.summary import formatear


def _resumen(**cambios):
    datos = {
        "archivo_nombre": "cuentas.csv",
        "archivo_hash": "a" * 64,
        "lineas_con_datos": 20,
        "lineas_en_blanco": 1,
        "repeticiones_ignoradas": 3,
        "ids_unicos": 17,
        "repetidos": [("7", 3), ("12", 2)],
        "por_estado": {
            Estado.PENDIENTE: 0,
            Estado.OK: 13,
            Estado.NO_ENCONTRADO: 3,
            Estado.DATO_INVALIDO: 1,
            Estado.ERROR_TECNICO: 0,
        },
        "errores_por_causa": {},
        "consultados": 16,
        "reutilizados": 0,
        "reintentos_totales": 0,
        "duracion_s": 1.234,
        "ruta_excel": Path("salida/consolidado_2026-10-23_aaaaaaaa.xlsx"),
    }
    datos.update(cambios)
    return ResumenEjecucion(**datos)


def test_el_bloque_del_reto_tiene_todas_las_secciones_y_respeta_el_ancho():
    texto = formatear(_resumen())
    lineas = texto.splitlines()

    assert lineas[0] == "=" * 62
    assert lineas[1] == " RESUMEN DE LA EJECUCIÓN"
    for seccion in [
        " ENTRADA",
        " RESULTADO POR ESTADO",
        " ERRORES TÉCNICOS POR CAUSA",
        " ESTA CORRIDA",
    ]:
        assert seccion in lineas

    assert " Archivo : cuentas.csv  (hash " + "a" * 8 in texto
    assert " Excel   : salida/consolidado_2026-10-23_aaaaaaaa.xlsx" in texto
    assert re.search(r"^   Líneas con datos \.+ +20$", texto, re.M)
    assert re.search(r"^   Líneas en blanco ignoradas \.+ +1$", texto, re.M)
    assert re.search(
        r"^   Repeticiones ignoradas \.+ +3 +\(7 x3, 12 x2\)$", texto, re.M
    )
    assert re.search(r"^   Identificadores únicos \.+ +17$", texto, re.M)
    assert re.search(r"^   OK \.+ +13$", texto, re.M)
    assert re.search(r"^   NO_ENCONTRADO \.+ +3$", texto, re.M)
    assert re.search(r"^   DATO_INVALIDO \.+ +1$", texto, re.M)
    assert re.search(r"^   ERROR_TECNICO \.+ +0$", texto, re.M)
    assert re.search(r"^   PENDIENTE \.+ +0$", texto, re.M)
    assert re.search(r"^   Total \.+ +17$", texto, re.M)
    assert "   (ninguno)" in texto
    assert re.search(r"^   Consultados \.+ +16$", texto, re.M)
    assert re.search(r"^   Reutilizados \.+ +0$", texto, re.M)
    assert re.search(r"^   Reintentos \.+ +0$", texto, re.M)
    assert re.search(r"^   Duración \.+ +1\.23 s$", texto, re.M)
    assert all(len(linea) <= 78 for linea in lineas)


def test_incluye_errores_por_causa():
    texto = formatear(
        _resumen(
            errores_por_causa={Causa.TIMEOUT: 2, Causa.CONEXION: 1},
            por_estado={Estado.ERROR_TECNICO: 3},
        )
    )

    assert re.search(r"^   CONEXION \.+ +1$", texto, re.M)
    assert re.search(r"^   TIMEOUT \.+ +2$", texto, re.M)
    assert "(ninguno)" not in texto
    assert re.search(r"^   ERROR_TECNICO \.+ +3$", texto, re.M)
    assert re.search(r"^   Total \.+ +3$", texto, re.M)


def test_sin_repetidos_ni_excel():
    texto = formatear(_resumen(repetidos=[], ruta_excel=None, errores_por_causa={}))

    assert " Excel   : no generado" in texto
    assert re.search(r"^   Repeticiones ignoradas \.+ +3$", texto, re.M)


def test_limita_las_lineas_largas_a_78_columnas():
    texto = formatear(
        _resumen(
            archivo_nombre="x" * 100,
            ruta_excel=Path("salida/" + "y" * 100 + ".xlsx"),
        )
    )
    lineas = texto.splitlines()

    assert all(len(linea) <= 78 for linea in lineas)
    assert lineas[3].endswith("...")
    assert lineas[4].endswith("...")
