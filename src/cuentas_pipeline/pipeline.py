import logging
import time

from cuentas_pipeline.core.config import Config
from cuentas_pipeline.core.models import Causa, Estado, Resultado, ResumenEjecucion
from cuentas_pipeline.steps.normalize import normalizar
from cuentas_pipeline.steps.resolve import resolver
from cuentas_pipeline.steps.summary import formatear

logger = logging.getLogger(__name__)

_ESTADOS_REUTILIZABLES = (Estado.OK.value, Estado.NO_ENCONTRADO.value)


def _conteos_por_estado(repo, archivo_hash: str) -> dict[Estado, int]:
    conteos = repo.conteos(archivo_hash)
    return {estado: conteos.get(estado, 0) for estado in Estado}


def _errores_por_causa(filas: list[dict[str, object]]) -> dict[Causa, int]:
    errores: dict[Causa, int] = {}
    for fila in filas:
        if fila["estado"] != Estado.ERROR_TECNICO.value:
            continue
        causa = Causa(fila["causa"])
        errores[causa] = errores.get(causa, 0) + 1
    return errores


def _reutilizables_previas(filas: list[dict[str, object]]) -> int:
    return sum(1 for fila in filas if fila["estado"] in _ESTADOS_REUTILIZABLES)


def _registrar_resultado(id_cuenta: str, resultado: Resultado) -> None:
    if resultado.estado is Estado.ERROR_TECNICO:
        logger.error(
            "id=%s estado=%s causa=%s intentos=%d",
            id_cuenta,
            resultado.estado.value,
            resultado.causa.value,
            resultado.intentos,
        )
    else:
        logger.info(
            "id=%s estado=%s causa=%s intentos=%d",
            id_cuenta,
            resultado.estado.value,
            resultado.causa.value if resultado.causa is not None else "-",
            resultado.intentos,
        )


def ejecutar(
    lectura,
    config: Config,
    repo,
    cliente,
    escritor=None,
    sleep=time.sleep,
) -> ResumenEjecucion:
    inicio = time.monotonic()
    logger.info("inicio archivo=%s hash8=%s", lectura.nombre, lectura.hash8)

    normalizacion = normalizar(lectura.filas)
    if normalizacion.lineas_con_datos == 0:
        logger.warning("entrada sin datos archivo=%s", lectura.nombre)

    reutilizados = _reutilizables_previas(repo.filas(lectura.archivo_hash))
    repo.cargar_filas(lectura.archivo_hash, lectura.nombre, normalizacion.filas)

    pendientes = repo.pendientes(lectura.archivo_hash)
    consultados = 0
    reintentos_totales = 0

    for indice, fila in enumerate(pendientes):
        try:
            resultado = resolver(cliente, fila.id, config.reintentos, sleep=sleep)
        except Exception as error:
            logger.exception("id=%s estado=ERROR_TECNICO causa=ERROR_INESPERADO", fila.id)
            resultado = Resultado(
                estado=Estado.ERROR_TECNICO,
                causa=Causa.ERROR_INESPERADO,
                intentos=0,
                detalle_error=f"{type(error).__name__}: {error}",
            )

        repo.guardar(lectura.archivo_hash, fila.id, resultado)
        consultados += 1
        reintentos_totales += max(resultado.intentos - 1, 0)
        _registrar_resultado(fila.id, resultado)

        if config.api.pausa_entre_consultas_s and indice < len(pendientes) - 1:
            sleep(config.api.pausa_entre_consultas_s)

    filas = repo.filas(lectura.archivo_hash)
    ruta_excel = None
    if escritor is not None:
        ruta_excel = escritor.escribir(
            lectura.nombre,
            lectura.archivo_hash,
            normalizacion,
            filas,
        )

    resumen = ResumenEjecucion(
        archivo_nombre=lectura.nombre,
        archivo_hash=lectura.archivo_hash,
        lineas_con_datos=normalizacion.lineas_con_datos,
        lineas_en_blanco=normalizacion.lineas_en_blanco,
        repeticiones_ignoradas=normalizacion.repeticiones_ignoradas,
        ids_unicos=len(normalizacion.filas),
        repetidos=normalizacion.repetidos,
        por_estado=_conteos_por_estado(repo, lectura.archivo_hash),
        errores_por_causa=_errores_por_causa(filas),
        consultados=consultados,
        reutilizados=reutilizados,
        reintentos_totales=reintentos_totales,
        duracion_s=time.monotonic() - inicio,
        ruta_excel=ruta_excel,
    )
    logger.info("resumen\n%s", formatear(resumen))
    return resumen
