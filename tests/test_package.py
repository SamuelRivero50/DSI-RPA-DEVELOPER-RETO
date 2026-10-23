import cuentas_pipeline
from cuentas_pipeline import adapters, core, steps


def test_paquete_importable():
    assert cuentas_pipeline.__version__ == "0.1.0"
    assert adapters is not None
    assert core is not None
    assert steps is not None
