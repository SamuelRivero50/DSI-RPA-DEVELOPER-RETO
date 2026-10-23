import csv
from dataclasses import dataclass
from hashlib import sha256
from io import StringIO
from pathlib import Path

from cuentas_pipeline.core.config import EntradaConfig


class ErrorEntrada(Exception):
    """El archivo de entrada no se puede leer o no tiene el formato esperado."""


@dataclass(frozen=True)
class LecturaCsv:
    nombre: str
    archivo_hash: str
    hash8: str
    filas: list[tuple[int, str]]


def leer_csv(ruta: str | Path, config: EntradaConfig) -> LecturaCsv:
    ruta = Path(ruta)
    try:
        contenido = ruta.read_bytes()
    except OSError as exc:
        raise ErrorEntrada(f"no se pudo leer el archivo {ruta}: {exc}") from exc

    archivo_hash = sha256(contenido).hexdigest()
    try:
        texto = contenido.decode(config.codificacion)
    except UnicodeDecodeError as exc:
        raise ErrorEntrada(
            f"el archivo {ruta} no se puede decodificar como {config.codificacion}"
        ) from exc

    reader = csv.reader(StringIO(texto, newline=""))
    try:
        encabezado = next(reader)
    except StopIteration as exc:
        raise ErrorEntrada(f"el archivo {ruta} está vacío") from exc

    columnas = [columna.strip() for columna in encabezado]
    if config.columna not in columnas:
        raise ErrorEntrada(f"el archivo {ruta} no contiene la columna {config.columna}")

    indice = columnas.index(config.columna)
    filas = []
    for fila in reader:
        valor = fila[indice] if indice < len(fila) else ""
        filas.append((reader.line_num, valor))

    return LecturaCsv(
        nombre=ruta.name,
        archivo_hash=archivo_hash,
        hash8=archivo_hash[:8],
        filas=filas,
    )
