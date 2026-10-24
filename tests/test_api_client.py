from cuentas_pipeline.adapters.api_client import ApiClient
from cuentas_pipeline.core.config import ApiConfig


class SesionFalsa:
    def __init__(self):
        self.llamadas = []
        self.cerrada = False
        self.respuesta = object()

    def get(self, url, timeout):
        self.llamadas.append((url, timeout))
        return self.respuesta

    def close(self):
        self.cerrada = True


def test_hace_un_get_con_url_y_timeouts():
    sesion = SesionFalsa()
    config = ApiConfig(
        url_base="https://ejemplo.test/posts/",
        timeout_conexion_s=1.5,
        timeout_lectura_s=3.0,
    )
    cliente = ApiClient(config, sesion)

    respuesta = cliente.obtener("42")

    assert respuesta is sesion.respuesta
    assert sesion.llamadas == [("https://ejemplo.test/posts/42", (1.5, 3.0))]


def test_cierra_la_sesion():
    sesion = SesionFalsa()
    cliente = ApiClient(ApiConfig(), sesion)

    cliente.cerrar()

    assert sesion.cerrada
