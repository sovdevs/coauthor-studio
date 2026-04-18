def run_pipeline(*args, **kwargs):
    from .service import run_pipeline as _run
    return _run(*args, **kwargs)


def analyze(*args, **kwargs):
    from .service import analyze as _analyze
    return _analyze(*args, **kwargs)


__all__ = ["run_pipeline", "analyze"]
