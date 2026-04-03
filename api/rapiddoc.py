"""RapiDoc HTML page for API documentation."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["docs"])

_RAPIDOC_ASSET = (
  Path(__file__).resolve().parent.parent / "webui" / "static" / "rapiddoc" / "rapidoc-min.js"
)

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
      spec-url="/api/openapi.json"
      header-color="#1a1a1a"
      primary-color="#007acc"
      load-fonts="false"
      theme="dark"
    ></rapi-doc>

    <script src="/api/static/rapiddoc/rapidoc-min.js"></script>
  </body>
</html>
"""


@router.get("/api/docs", response_class=HTMLResponse)
async def get_rapiddoc() -> str:
    """RapiDoc API documentation UI."""
    return RAPIDDOC_HTML


@router.get("/api/static/rapiddoc/rapidoc-min.js")
async def get_rapiddoc_asset() -> FileResponse:
  """Serve the local RapiDoc bundle without external CDN dependencies."""

  return FileResponse(_RAPIDOC_ASSET, media_type="text/javascript")
