"""Tool modules by pipeline phase; server.register_all wires them."""
from . import discovery, generation, testing


def register_all(app):
    discovery.register(app)
    generation.register(app)
    testing.register(app)
