import os
import tempfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from cuentas_pipeline.core.config import SalidaConfig
from cuentas_pipeline.core.models import Estado

_COLUMNAS = [
    "linea_origen",
    "valor_original",
    "id_cuenta",
    "estado",
    "causa",
    "apariciones",
    "user_id",
    "titulo",
    "cuerpo",
    "intentos",
    "detalle_error",
    "consultado_en",
]

_PREFIJOS_FORMULA = ("=", "+", "-", "@")

_RELLENOS = {
    Estado.OK.value: "C6EFCE",
    Estado.NO_ENCONTRADO.value: "FFEB9C",
    Estado.DATO_INVALIDO.value: "F8CBAD",
    Estado.ERROR_TECNICO.value: "FFC7CE",
    Estado.PENDIENTE.value: "D9D9D9",
}

_ANCHOS = [14, 18, 12, 18, 18, 12, 10, 30, 50, 10, 40, 26]


def _fecha_archivo(filas: list[dict[str, object]]) -> str:
    fechas = [str(fila["creado_en"]) for fila in filas if fila.get("creado_en")]
    if not fechas:
        return datetime.now().astimezone().date().isoformat()
    return min(fechas)[:10]


def _valores(fila: dict[str, object]) -> list[object]:
    estado = str(fila["estado"])
    id_cuenta = None if estado == Estado.DATO_INVALIDO.value else int(fila["id"])
    return [
        fila["linea_origen"],
        fila["valor_original"],
        id_cuenta,
        estado,
        fila["causa"],
        fila["apariciones"],
        fila["user_id"],
        fila["titulo"],
        fila["cuerpo"],
        fila["intentos"],
        fila["detalle_error"],
        fila["actualizado_en"],
    ]


def _proteger_texto(celda) -> None:
    if isinstance(celda.value, str) and celda.value.startswith(_PREFIJOS_FORMULA):
        celda.data_type = "s"


def _escribir_celda(hoja, fila: int, columna: int, valor, negrita: bool = False):
    celda = hoja.cell(row=fila, column=columna, value=valor)
    if negrita:
        celda.font = Font(bold=True)
    _proteger_texto(celda)
    return celda


def _primera_carga(filas: list[dict[str, object]]) -> str:
    fechas = [str(fila["creado_en"]) for fila in filas if fila.get("creado_en")]
    return min(fechas) if fechas else ""


def _conteos_por_estado(filas: list[dict[str, object]]) -> dict[str, int]:
    conteos = {estado.value: 0 for estado in Estado}
    for fila in filas:
        conteos[str(fila["estado"])] += 1
    return conteos


def _conteos_por_causa(filas: list[dict[str, object]]) -> dict[str, int]:
    conteos: dict[str, int] = {}
    for fila in filas:
        if fila["estado"] != Estado.ERROR_TECNICO.value or not fila["causa"]:
            continue
        causa = str(fila["causa"])
        conteos[causa] = conteos.get(causa, 0) + 1
    return dict(sorted(conteos.items()))


def _escribir_resumen(
    libro,
    archivo_nombre: str,
    archivo_hash: str,
    normalizacion,
    filas: list[dict[str, object]],
    generado_en: str,
) -> None:
    hoja = libro.create_sheet("Resumen")
    hoja.column_dimensions["A"].width = 34
    hoja.column_dimensions["B"].width = 70
    fila = 1

    _escribir_celda(hoja, fila, 1, "Archivo", True)
    fila += 1
    for etiqueta, valor in [
        ("nombre", archivo_nombre),
        ("hash", archivo_hash),
        ("primera carga", _primera_carga(filas)),
        ("generado en", generado_en),
    ]:
        _escribir_celda(hoja, fila, 1, etiqueta)
        _escribir_celda(hoja, fila, 2, valor)
        fila += 1

    fila += 1
    _escribir_celda(hoja, fila, 1, "Entrada", True)
    fila += 1
    for etiqueta, valor in [
        ("lineas con datos", normalizacion.lineas_con_datos),
        ("lineas en blanco ignoradas", normalizacion.lineas_en_blanco),
        ("repeticiones ignoradas", normalizacion.repeticiones_ignoradas),
        ("ids unicos", len(normalizacion.filas)),
    ]:
        _escribir_celda(hoja, fila, 1, etiqueta)
        _escribir_celda(hoja, fila, 2, valor)
        fila += 1

    fila += 1
    _escribir_celda(hoja, fila, 1, "Resultado por estado", True)
    fila += 1
    _escribir_celda(hoja, fila, 1, "estado", True)
    _escribir_celda(hoja, fila, 2, "total", True)
    fila += 1
    for estado, total in _conteos_por_estado(filas).items():
        _escribir_celda(hoja, fila, 1, estado)
        _escribir_celda(hoja, fila, 2, total)
        fila += 1

    fila += 1
    _escribir_celda(hoja, fila, 1, "Errores tecnicos por causa", True)
    fila += 1
    _escribir_celda(hoja, fila, 1, "causa", True)
    _escribir_celda(hoja, fila, 2, "total", True)
    fila += 1
    errores = _conteos_por_causa(filas)
    if errores:
        for causa, total in errores.items():
            _escribir_celda(hoja, fila, 1, causa)
            _escribir_celda(hoja, fila, 2, total)
            fila += 1
    else:
        _escribir_celda(hoja, fila, 1, "ninguno")
        fila += 1

    fila += 1
    _escribir_celda(hoja, fila, 1, "Repetidos", True)
    fila += 1
    _escribir_celda(hoja, fila, 1, "id", True)
    _escribir_celda(hoja, fila, 2, "apariciones", True)
    fila += 1
    if normalizacion.repetidos:
        for id_cuenta, apariciones in normalizacion.repetidos:
            _escribir_celda(hoja, fila, 1, id_cuenta)
            _escribir_celda(hoja, fila, 2, apariciones)
            fila += 1
    else:
        _escribir_celda(hoja, fila, 1, "ninguno")


class ExcelWriter:
    def __init__(self, config: SalidaConfig):
        self._carpeta = Path(config.carpeta)

    def escribir(
        self,
        archivo_nombre: str,
        archivo_hash: str,
        normalizacion,
        filas: list[dict[str, object]],
    ) -> Path:
        self._carpeta.mkdir(parents=True, exist_ok=True)
        fecha = _fecha_archivo(filas)
        ruta = self._carpeta / f"consolidado_{fecha}_{archivo_hash[:8]}.xlsx"

        descriptor, nombre_temporal = tempfile.mkstemp(
            prefix=".consolidado_",
            suffix=".xlsx",
            dir=self._carpeta,
        )
        os.close(descriptor)
        temporal = Path(nombre_temporal)

        try:
            libro = Workbook()
            hoja = libro.active
            hoja.title = "Resultados"
            hoja.append(_COLUMNAS)
            for celda in hoja[1]:
                celda.font = Font(bold=True)

            for fila in filas:
                hoja.append(_valores(fila))
                relleno = PatternFill(
                    fill_type="solid",
                    start_color=_RELLENOS[str(fila["estado"])],
                    end_color=_RELLENOS[str(fila["estado"])],
                )
                for celda in hoja[hoja.max_row]:
                    _proteger_texto(celda)
                    celda.fill = relleno
                hoja.cell(row=hoja.max_row, column=9).alignment = Alignment(
                    wrap_text=True, vertical="top"
                )

            for indice, ancho in enumerate(_ANCHOS, start=1):
                hoja.column_dimensions[get_column_letter(indice)].width = ancho

            hoja.freeze_panes = "A2"
            hoja.auto_filter.ref = f"A1:L{hoja.max_row}"

            _escribir_resumen(
                libro,
                archivo_nombre,
                archivo_hash,
                normalizacion,
                filas,
                datetime.now().astimezone().isoformat(timespec="seconds"),
            )

            libro.save(temporal)
            os.replace(temporal, ruta)
        finally:
            if temporal.exists():
                temporal.unlink()

        return ruta
