from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="nightfall-photo-ingress API")
    return app


app = create_app()
