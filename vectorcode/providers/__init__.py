"""VECTOR providers."""

def get_model_router():
    from vectorcode.src.router import GNNRouter
    return GNNRouter()
