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

            libro.save(temporal)
            os.replace(temporal, ruta)
        finally:
            if temporal.exists():
                temporal.unlink()

        return ruta
