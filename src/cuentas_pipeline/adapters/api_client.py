import requests

from cuentas_pipeline.core.config import ApiConfig


class ApiClient:
    def __init__(self, config: ApiConfig, session: requests.Session | None = None):
        self._url_base = config.url_base.rstrip("/")
        self._timeout = (config.timeout_conexion_s, config.timeout_lectura_s)
        self._session = session or requests.Session()

    def obtener(self, id_cuenta: str) -> requests.Response:
        return self._session.get(f"{self._url_base}/{id_cuenta}", timeout=self._timeout)

    def cerrar(self) -> None:
        self._session.close()
