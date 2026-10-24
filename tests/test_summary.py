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


def test_incluye_archivo_entrada_resultados_y_corrida():
    texto = formatear(_resumen())

    assert "archivo=cuentas.csv hash=" + "a" * 64 in texto
    assert "lineas_con_datos=20 lineas_en_blanco=1" in texto
    assert "repeticiones_ignoradas=3 ids_unicos=17" in texto
    assert "repetidos: 7 x3, 12 x2" in texto
    assert "resultado: PENDIENTE=0 OK=13 NO_ENCONTRADO=3 DATO_INVALIDO=1 ERROR_TECNICO=0" in texto
    assert "errores_tecnicos: ninguno" in texto
    assert "corrida: consultados=16 reutilizados=0 reintentos=0 duracion_s=1.23" in texto
    assert "excel=salida/consolidado_2026-10-23_aaaaaaaa.xlsx" in texto


def test_incluye_errores_por_causa():
    texto = formatear(
        _resumen(
            errores_por_causa={Causa.TIMEOUT: 2, Causa.CONEXION: 1},
            por_estado={Estado.ERROR_TECNICO: 3},
        )
    )

    assert "errores_tecnicos: CONEXION=1, TIMEOUT=2" in texto
    assert "PENDIENTE=0 OK=0 NO_ENCONTRADO=0 DATO_INVALIDO=0 ERROR_TECNICO=3" in texto


def test_sin_repetidos_ni_excel():
    texto = formatear(
        _resumen(repetidos=[], ruta_excel=None, errores_por_causa={})
    )

    assert "repetidos: ninguno" in texto
    assert "excel=no generado" in texto
