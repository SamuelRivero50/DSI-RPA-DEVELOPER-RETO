from cuentas_pipeline.core.models import Causa, Estado, FilaCuenta, Resultado


def test_estados_y_causas_son_texto():
    assert Estado.OK == "OK"
    assert Estado.DATO_INVALIDO == "DATO_INVALIDO"
    assert Causa.HTTP_404 == "HTTP_404"
    assert Causa.FORMATO_INVALIDO == "FORMATO_INVALIDO"


def test_fila_cuenta_por_defecto_es_valida():
    fila = FilaCuenta(linea_origen=4, valor_original=" 23 ", id="23")
    assert fila.valida
    assert fila.apariciones == 1


def test_resultado_por_defecto_sin_datos_de_api():
    resultado = Resultado(estado=Estado.NO_ENCONTRADO, causa=Causa.HTTP_404, intentos=1)
    assert resultado.user_id is None
    assert resultado.causa is Causa.HTTP_404
