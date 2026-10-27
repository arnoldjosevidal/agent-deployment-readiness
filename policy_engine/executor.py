"""Entrada compatible para regresión de la interfaz histórica, sin proveedor."""
from adr_g64r.events import TracedExecutor

class PolicyAwareToolsExecutor(TracedExecutor):
    def __init__(self,policy,*,authorized_context=None):
        super().__init__(policy,authorized_context=authorized_context)
