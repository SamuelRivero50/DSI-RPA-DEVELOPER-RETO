from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Estado(StrEnum):
    PENDIENTE = "PENDIENTE"
    OK = "OK"
    NO_ENCONTRADO = "NO_ENCONTRADO"
    DATO_INVALIDO = "DATO_INVALIDO"
    ERROR_TECNICO = "ERROR_TECNICO"


class Causa(StrEnum):
    HTTP_404 = "HTTP_404"
    FORMATO_INVALIDO = "FORMATO_INVALIDO"
    TIMEOUT = "TIMEOUT"
    CONEXION = "CONEXION"
    HTTP_5XX = "HTTP_5XX"
    HTTP_429 = "HTTP_429"
    HTTP_4XX = "HTTP_4XX"
    RESPUESTA_INVALIDA = "RESPUESTA_INVALIDA"
    ERROR_INESPERADO = "ERROR_INESPERADO"


@dataclass(frozen=True)
class FilaCuenta:
    linea_origen: int
    valor_original: str
    id: str
    apariciones: int = 1
    valida: bool = True


@dataclass(frozen=True)
class Resultado:
    estado: Estado
    causa: Causa | None = None
    user_id: int | None = None
    titulo: str | None = None
    cuerpo: str | None = None
    intentos: int = 0
    detalle_error: str | None = None


@dataclass(frozen=True)
class ResumenEjecucion:
    archivo_nombre: str
    archivo_hash: str
    lineas_con_datos: int
    lineas_en_blanco: int
    repeticiones_ignoradas: int
    ids_unicos: int
    repetidos: list[tuple[str, int]] = field(default_factory=list)
    por_estado: dict[Estado, int] = field(default_factory=dict)
    errores_por_causa: dict[Causa, int] = field(default_factory=dict)
    consultados: int = 0
    reutilizados: int = 0
    reintentos_totales: int = 0
    duracion_s: float = 0.0
    ruta_excel: Path | None = None
