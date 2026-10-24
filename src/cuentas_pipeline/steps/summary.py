from cuentas_pipeline.core.models import Estado, ResumenEjecucion

_ANCHO_MAXIMO = 78
_SEPARADOR = "=" * 62
_ANCHO_ETIQUETA = 33
_ANCHO_VALOR = 2

_ORDEN_ESTADOS = (
    Estado.OK,
    Estado.NO_ENCONTRADO,
    Estado.DATO_INVALIDO,
    Estado.ERROR_TECNICO,
    Estado.PENDIENTE,
)


def _limitar(texto: str) -> str:
    if len(texto) <= _ANCHO_MAXIMO:
        return texto
    return texto[: _ANCHO_MAXIMO - 3] + "..."


def _linea(etiqueta: str, valor, sufijo: str = "") -> str:
    prefijo = f"   {etiqueta} "
    puntos = "." * max(3, _ANCHO_ETIQUETA - len(prefijo))
    texto = f"{prefijo}{puntos}  {valor:>{_ANCHO_VALOR}}"
    if sufijo:
        texto += f"   {sufijo}"
    return _limitar(texto)


def _repetidos(repetidos: list[tuple[str, int]]) -> str:
    return ", ".join(f"{id_cuenta} x{apariciones}" for id_cuenta, apariciones in repetidos)


def formatear(resumen: ResumenEjecucion) -> str:
    excel = str(resumen.ruta_excel) if resumen.ruta_excel is not None else "no generado"
    repetidos = f"({_repetidos(resumen.repetidos)})" if resumen.repetidos else ""
    total = sum(resumen.por_estado.get(estado, 0) for estado in Estado)

    lineas = [
        _SEPARADOR,
        " RESUMEN DE LA EJECUCIÓN",
        _SEPARADOR,
        _limitar(f" Archivo : {resumen.archivo_nombre}  (hash {resumen.archivo_hash[:8]})"),
        _limitar(f" Excel   : {excel}"),
        "",
        " ENTRADA",
        _linea("Líneas con datos", resumen.lineas_con_datos),
        _linea("Líneas en blanco ignoradas", resumen.lineas_en_blanco),
        _linea("Repeticiones ignoradas", resumen.repeticiones_ignoradas, repetidos),
        _linea("Identificadores únicos", resumen.ids_unicos),
        "",
        " RESULTADO POR ESTADO",
    ]

    for estado in _ORDEN_ESTADOS:
        lineas.append(_linea(estado.value, resumen.por_estado.get(estado, 0)))
    lineas.append(_linea("Total", total))

    lineas.extend(["", " ERRORES TÉCNICOS POR CAUSA"])
    if resumen.errores_por_causa:
        for causa, cantidad in sorted(
            resumen.errores_por_causa.items(), key=lambda item: item[0].value
        ):
            lineas.append(_linea(causa.value, cantidad))
    else:
        lineas.append("   (ninguno)")

    lineas.extend(
        [
            "",
            " ESTA CORRIDA",
            _linea("Consultados", resumen.consultados),
            _linea("Reutilizados", resumen.reutilizados),
            _linea("Reintentos", resumen.reintentos_totales),
            _linea("Duración", f"{resumen.duracion_s:.2f} s"),
            _SEPARADOR,
        ]
    )
    return "\n".join(lineas)
