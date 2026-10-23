import codecs
from dataclasses import dataclass, field
from typing import Any


class ConfigInvalidaError(ValueError):
    """La configuración no cumple el contrato esperado."""


@dataclass(frozen=True)
class EntradaConfig:
    archivo: str = "cuentas.csv"
    columna: str = "id_cuenta"
    codificacion: str = "utf-8-sig"


@dataclass(frozen=True)
class ApiConfig:
    url_base: str = "https://jsonplaceholder.typicode.com/posts"
    timeout_conexion_s: float = 5.0
    timeout_lectura_s: float = 10.0
    pausa_entre_consultas_s: float = 0.0


@dataclass(frozen=True)
class ReintentosConfig:
    max_intentos: int = 4
    espera_base_s: float = 1.0
    factor: float = 2.0
    espera_maxima_s: float = 30.0
    retry_after_maximo_s: float = 60.0


@dataclass(frozen=True)
class SalidaConfig:
    carpeta: str = "salida"
    base_datos: str = "estado/estado.db"


@dataclass(frozen=True)
class LogConfig:
    archivo: str = "logs/proceso.log"
    nivel: str = "INFO"
    max_bytes: int = 5_242_880
    copias: int = 5


@dataclass(frozen=True)
class Config:
    entrada: EntradaConfig = field(default_factory=EntradaConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    reintentos: ReintentosConfig = field(default_factory=ReintentosConfig)
    salida: SalidaConfig = field(default_factory=SalidaConfig)
    log: LogConfig = field(default_factory=LogConfig)


_NIVELES_LOG = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _seccion(datos: dict[str, Any], nombre: str, permitidas: set[str]) -> dict[str, Any]:
    valor = datos.get(nombre, {})
    if not isinstance(valor, dict):
        raise ConfigInvalidaError(f"[{nombre}] debe ser una sección TOML")
    desconocidas = set(valor) - permitidas
    if desconocidas:
        claves = ", ".join(sorted(desconocidas))
        raise ConfigInvalidaError(f"[{nombre}] claves desconocidas: {claves}")
    return valor


def _texto(datos: dict[str, Any], seccion: str, clave: str, defecto: str) -> str:
    valor = datos.get(clave, defecto)
    if not isinstance(valor, str) or not valor.strip():
        raise ConfigInvalidaError(f"[{seccion}] {clave} debe ser texto no vacío")
    return valor


def _numero(
    datos: dict[str, Any],
    seccion: str,
    clave: str,
    defecto: float,
    *,
    entero: bool = False,
    minimo: float | None = None,
    estricto: bool = False,
) -> float:
    valor = datos.get(clave, defecto)
    tipos = (int,) if entero else (int, float)
    if isinstance(valor, bool) or not isinstance(valor, tipos):
        tipo = "entero" if entero else "número"
        raise ConfigInvalidaError(f"[{seccion}] {clave} debe ser un {tipo}")
    if minimo is not None:
        if estricto and valor <= minimo:
            raise ConfigInvalidaError(f"[{seccion}] {clave} debe ser mayor que {minimo}")
        if not estricto and valor < minimo:
            raise ConfigInvalidaError(f"[{seccion}] {clave} debe ser mayor o igual que {minimo}")
    return valor


def config_desde_dict(datos: dict[str, Any]) -> Config:
    if not isinstance(datos, dict):
        raise ConfigInvalidaError("la configuración debe ser una tabla TOML")

    secciones = {"entrada", "api", "reintentos", "salida", "log"}
    desconocidas = set(datos) - secciones
    if desconocidas:
        claves = ", ".join(sorted(desconocidas))
        raise ConfigInvalidaError(f"secciones desconocidas: {claves}")

    entrada = _seccion(datos, "entrada", {"archivo", "columna", "codificacion"})
    codificacion = _texto(entrada, "entrada", "codificacion", "utf-8-sig")
    try:
        codecs.lookup(codificacion)
    except LookupError as exc:
        raise ConfigInvalidaError(
            f"[entrada] codificacion desconocida: {codificacion}"
        ) from exc

    api = _seccion(
        datos,
        "api",
        {"url_base", "timeout_conexion_s", "timeout_lectura_s", "pausa_entre_consultas_s"},
    )
    reintentos = _seccion(
        datos,
        "reintentos",
        {"max_intentos", "espera_base_s", "factor", "espera_maxima_s", "retry_after_maximo_s"},
    )
    salida = _seccion(datos, "salida", {"carpeta", "base_datos"})
    log = _seccion(datos, "log", {"archivo", "nivel", "max_bytes", "copias"})

    nivel = _texto(log, "log", "nivel", "INFO").upper()
    if nivel not in _NIVELES_LOG:
        raise ConfigInvalidaError(f"[log] nivel inválido: {nivel}")

    return Config(
        entrada=EntradaConfig(
            archivo=_texto(entrada, "entrada", "archivo", "cuentas.csv"),
            columna=_texto(entrada, "entrada", "columna", "id_cuenta"),
            codificacion=codificacion,
        ),
        api=ApiConfig(
            url_base=_texto(api, "api", "url_base", "https://jsonplaceholder.typicode.com/posts"),
            timeout_conexion_s=_numero(
                api, "api", "timeout_conexion_s", 5.0, minimo=0, estricto=True
            ),
            timeout_lectura_s=_numero(
                api, "api", "timeout_lectura_s", 10.0, minimo=0, estricto=True
            ),
            pausa_entre_consultas_s=_numero(
                api, "api", "pausa_entre_consultas_s", 0.0, minimo=0
            ),
        ),
        reintentos=ReintentosConfig(
            max_intentos=_numero(
                reintentos, "reintentos", "max_intentos", 4, entero=True, minimo=1
            ),
            espera_base_s=_numero(reintentos, "reintentos", "espera_base_s", 1.0, minimo=0),
            factor=_numero(reintentos, "reintentos", "factor", 2.0, minimo=1.0),
            espera_maxima_s=_numero(
                reintentos, "reintentos", "espera_maxima_s", 30.0, minimo=0
            ),
            retry_after_maximo_s=_numero(
                reintentos, "reintentos", "retry_after_maximo_s", 60.0, minimo=0
            ),
        ),
        salida=SalidaConfig(
            carpeta=_texto(salida, "salida", "carpeta", "salida"),
            base_datos=_texto(salida, "salida", "base_datos", "estado/estado.db"),
        ),
        log=LogConfig(
            archivo=_texto(log, "log", "archivo", "logs/proceso.log"),
            nivel=nivel,
            max_bytes=_numero(
                log, "log", "max_bytes", 5_242_880, entero=True, minimo=1
            ),
            copias=_numero(log, "log", "copias", 5, entero=True, minimo=1),
        ),
    )
