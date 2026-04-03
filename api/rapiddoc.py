"""RapiDoc HTML page for API documentation."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["docs"])

RAPIDDOC_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>nightfall-photo-ingress API - RapiDoc</title>
    <style>
      html {
        height: 100%;
        overflow: hidden;
      }
      body {
        margin: 0;
        padding: 0;
        height: 100%;
        overflow: hidden;
        font-family: sans-serif;
      }
    </style>
  </head>
  <body>
    <rapi-doc
      spec-url="./openapi.json"
      header-color="#1a1a1a"
      primary-color="#007acc"
      load-fonts="false"
      theme="dark"
    ></rapi-doc>

    <script src="https://cdn.jsdelivr.net/npm/rapidoc@9.3.4/dist/rapidoc-min.js"></script>
  </body>
</html>
"""


@router.get("/api/docs", response_class=HTMLResponse)
async def get_rapiddoc() -> str:
    """RapiDoc API documentation UI."""
    return RAPIDDOC_HTML
