import re
from collections.abc import Iterable
from dataclasses import dataclass, replace

from cuentas_pipeline.core.models import FilaCuenta

_PATRON_ENTERO = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class Normalizacion:
    filas: list[FilaCuenta]
    lineas_con_datos: int
    lineas_en_blanco: int
    repeticiones_ignoradas: int
    repetidos: list[tuple[str, int]]


def normalizar(filas: Iterable[tuple[int, str]]) -> Normalizacion:
    unicas: dict[str, FilaCuenta] = {}
    lineas_con_datos = 0
    lineas_en_blanco = 0

    for linea_origen, valor_original in filas:
        texto = valor_original.strip()
        if not texto:
            lineas_en_blanco += 1
            continue

        lineas_con_datos += 1
        valida = _PATRON_ENTERO.fullmatch(texto) is not None
        id_cuenta = str(int(texto)) if valida else texto

        if id_cuenta in unicas:
            anterior = unicas[id_cuenta]
            unicas[id_cuenta] = replace(anterior, apariciones=anterior.apariciones + 1)
        else:
            unicas[id_cuenta] = FilaCuenta(
                linea_origen=linea_origen,
                valor_original=valor_original,
                id=id_cuenta,
                valida=valida,
            )

    filas_ordenadas = sorted(unicas.values(), key=lambda fila: fila.linea_origen)
    repetidos = [(fila.id, fila.apariciones) for fila in filas_ordenadas if fila.apariciones > 1]
    repeticiones_ignoradas = sum(fila.apariciones - 1 for fila in filas_ordenadas)

    return Normalizacion(
        filas=filas_ordenadas,
        lineas_con_datos=lineas_con_datos,
        lineas_en_blanco=lineas_en_blanco,
        repeticiones_ignoradas=repeticiones_ignoradas,
        repetidos=repetidos,
    )
