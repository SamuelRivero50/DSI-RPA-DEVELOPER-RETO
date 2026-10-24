import sqlite3
from datetime import datetime
from pathlib import Path

from cuentas_pipeline.core.config import SalidaConfig
from cuentas_pipeline.core.models import Causa, Estado, FilaCuenta, Resultado

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS resultados (
  archivo_hash   TEXT NOT NULL,
  id             TEXT NOT NULL,
  archivo_nombre TEXT NOT NULL,
  linea_origen   INTEGER NOT NULL,
  valor_original TEXT NOT NULL,
  estado         TEXT NOT NULL CHECK (estado IN (
                     'PENDIENTE','OK','NO_ENCONTRADO','DATO_INVALIDO','ERROR_TECNICO'
                 )),
  causa          TEXT,
  apariciones    INTEGER NOT NULL DEFAULT 1,
  user_id        INTEGER,
  titulo         TEXT,
  cuerpo         TEXT,
  intentos       INTEGER NOT NULL DEFAULT 0,
  detalle_error  TEXT,
  creado_en      TEXT NOT NULL,
  actualizado_en TEXT NOT NULL,
  PRIMARY KEY (archivo_hash, id)
);
"""

_INSERTAR = """
INSERT OR IGNORE INTO resultados (
  archivo_hash, id, archivo_nombre, linea_origen, valor_original,
  estado, causa, apariciones, intentos, creado_en, actualizado_en
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
"""


def _ahora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Repositorio:
    def __init__(self, config: SalidaConfig):
        ruta = Path(config.base_datos)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self._conexion = sqlite3.connect(ruta)
        self._conexion.row_factory = sqlite3.Row
        self._conexion.execute("PRAGMA journal_mode=WAL")
        self._conexion.execute("PRAGMA synchronous=FULL")
        self._conexion.execute(_ESQUEMA)
        self._conexion.commit()

    def cerrar(self) -> None:
        self._conexion.close()

    def cargar_filas(
        self,
        archivo_hash: str,
        archivo_nombre: str,
        filas: list[FilaCuenta],
    ) -> None:
        ahora = _ahora()
        registros = []
        for fila in filas:
            if fila.valida:
                estado = Estado.PENDIENTE.value
                causa = None
            else:
                estado = Estado.DATO_INVALIDO.value
                causa = Causa.FORMATO_INVALIDO.value
            registros.append(
                (
                    archivo_hash,
                    fila.id,
                    archivo_nombre,
                    fila.linea_origen,
                    fila.valor_original,
                    estado,
                    causa,
                    fila.apariciones,
                    ahora,
                    ahora,
                )
            )

        with self._conexion:
            self._conexion.executemany(_INSERTAR, registros)

    def pendientes(self, archivo_hash: str) -> list[FilaCuenta]:
        cursor = self._conexion.execute(
            """
            SELECT id, linea_origen, valor_original, apariciones
            FROM resultados
            WHERE archivo_hash = ? AND estado IN (?, ?)
            ORDER BY linea_origen
            """,
            (archivo_hash, Estado.PENDIENTE.value, Estado.ERROR_TECNICO.value),
        )
        return [
            FilaCuenta(
                linea_origen=int(registro["linea_origen"]),
                valor_original=registro["valor_original"],
                id=registro["id"],
                apariciones=int(registro["apariciones"]),
                valida=True,
            )
            for registro in cursor
        ]

    def guardar(self, archivo_hash: str, id_cuenta: str, resultado: Resultado) -> None:
        with self._conexion:
            self._conexion.execute(
                """
                UPDATE resultados
                SET estado = ?, causa = ?, user_id = ?, titulo = ?, cuerpo = ?,
                    intentos = ?, detalle_error = ?, actualizado_en = ?
                WHERE archivo_hash = ? AND id = ?
                """,
                (
                    resultado.estado.value,
                    resultado.causa.value if resultado.causa is not None else None,
                    resultado.user_id,
                    resultado.titulo,
                    resultado.cuerpo,
                    resultado.intentos,
                    resultado.detalle_error,
                    _ahora(),
                    archivo_hash,
                    id_cuenta,
                ),
            )

    def filas(self, archivo_hash: str) -> list[dict[str, object]]:
        cursor = self._conexion.execute(
            """
            SELECT *
            FROM resultados
            WHERE archivo_hash = ?
            ORDER BY linea_origen
            """,
            (archivo_hash,),
        )
        return [dict(registro) for registro in cursor]

    def conteos(self, archivo_hash: str) -> dict[Estado, int]:
        cursor = self._conexion.execute(
            """
            SELECT estado, COUNT(*) AS total
            FROM resultados
            WHERE archivo_hash = ?
            GROUP BY estado
            """,
            (archivo_hash,),
        )
        return {Estado(registro["estado"]): int(registro["total"]) for registro in cursor}
