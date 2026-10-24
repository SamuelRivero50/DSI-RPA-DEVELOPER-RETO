from cuentas_pipeline.core.models import Estado, ResumenEjecucion


def _repetidos(repetidos: list[tuple[str, int]]) -> str:
    if not repetidos:
        return "ninguno"
    return ", ".join(f"{id_cuenta} x{apariciones}" for id_cuenta, apariciones in repetidos)


def _errores(errores_por_causa: dict) -> str:
    if not errores_por_causa:
        return "ninguno"
    return ", ".join(
        f"{causa.value}={total}"
        for causa, total in sorted(errores_por_causa.items(), key=lambda item: item[0].value)
    )


def formatear(resumen: ResumenEjecucion) -> str:
    por_estado = " ".join(
        f"{estado.value}={resumen.por_estado.get(estado, 0)}" for estado in Estado
    )
    excel = str(resumen.ruta_excel) if resumen.ruta_excel is not None else "no generado"

    return "\n".join(
        [
            f"archivo={resumen.archivo_nombre} hash={resumen.archivo_hash}",
            (
                f"entrada: lineas_con_datos={resumen.lineas_con_datos} "
                f"lineas_en_blanco={resumen.lineas_en_blanco} "
                f"repeticiones_ignoradas={resumen.repeticiones_ignoradas} "
                f"ids_unicos={resumen.ids_unicos}"
            ),
            f"repetidos: {_repetidos(resumen.repetidos)}",
            f"resultado: {por_estado}",
            f"errores_tecnicos: {_errores(resumen.errores_por_causa)}",
            (
                f"corrida: consultados={resumen.consultados} "
                f"reutilizados={resumen.reutilizados} "
                f"reintentos={resumen.reintentos_totales} "
                f"duracion_s={resumen.duracion_s:.2f}"
            ),
            f"excel={excel}",
        ]
    )
