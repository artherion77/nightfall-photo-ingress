# Bundle Stats Handover Contract

Status: Active
Scope: Pipeline support prerequisite for Chunk 4 (bundle analysis collector)

## Producer contract

The frontend producer must generate `bundle-stats.json` whenever `pnpm build` is run from `webui/`.

Required producer behavior:
- Build command: `pnpm build`
- Producer plugin stack includes `rollup-plugin-visualizer` in JSON mode
- Producer emits parser-compatible `bundle-stats.json` with schema version 1
- Preferred output path: `webui/dist/bundle-stats.json`

Fallback candidate paths supported by consumer parser:
- `frontend/dist/bundle-stats.json`
- `metrics/dashboard/dist/bundle-stats.json`

## Required JSON shape (schema version 1)

```json
{
  "schema_version": 1,
  "chunks": [
    {
      "name": "assets/index.js",
      "type": "js",
      "raw_bytes": 12345,
      "gzip_bytes": 4567,
      "brotli_bytes": 3890,
      "modules": [
        {
          "id": "src/main.ts",
          "rendered_bytes": 2222
        }
      ]
    }
  ]
}
```

## Consumer expectations

Consumer location: `metrics/runner/module8_ops.py`

Consumer behavior:
- Scans candidate paths in priority order (`webui/`, `frontend/`, `metrics/dashboard/`)
- Parses only schema version 1
- Expects `chunks` array with per-chunk bytes and optional module breakdown
- Returns `status: available` when parse succeeds

## Failure modes

1. Missing file
- Symptom: collector status `not_available`
- Reason: `bundle-stats.json not found; run frontend build with bundle visualizer enabled`
- Action: run `pnpm build` in `webui/` and confirm `dist/bundle-stats.json` exists

2. Invalid schema
- Symptom: collector status `not_available`
- Reason: parse error (`unsupported bundle-stats.json schema`)
- Action: ensure producer emits `schema_version: 1` and `chunks` array

3. Invalid payload shape
- Symptom: collector status `not_available`
- Reason: parse error (`missing 'chunks' array` or field/type mismatch)
- Action: validate JSON against this contract before collection

## Audit checklist

- `pnpm build` succeeds in `webui/`
- `webui/dist/bundle-stats.json` exists
- `bundle-stats.json` is valid JSON
- parser `_parse_bundle_stats()` accepts payload without exception
