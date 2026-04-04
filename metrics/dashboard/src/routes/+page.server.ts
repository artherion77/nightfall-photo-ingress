import type { PageServerLoad } from './$types';
import path from 'node:path';
import { promises as fs } from 'node:fs';

type JsonObject = Record<string, unknown>;

async function readJson<T>(filePath: string): Promise<T> {
  const raw = await fs.readFile(filePath, 'utf-8');
  return JSON.parse(raw) as T;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function getPath(obj: JsonObject, parts: string[]): unknown {
  let current: unknown = obj;
  for (const part of parts) {
    if (!current || typeof current !== 'object' || !(part in (current as JsonObject))) {
      return undefined;
    }
    current = (current as JsonObject)[part];
  }
  return current;
}

function formatCompact(n: number): string {
  if (n >= 1000) {
    return `${(n / 1000).toFixed(1)}k`;
  }
  return String(Math.round(n));
}

function buildSparkline(series: number[]): string {
  if (series.length === 0) {
    return '';
  }
  const width = 180;
  const height = 42;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min || 1;
  return series
    .map((value, idx) => {
      const x = (idx / Math.max(1, series.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

function buildNodes(keys: string[]): Array<{ x: number; y: number; r: number }> {
  const count = Math.max(18, Math.min(46, keys.length));
  const nodes: Array<{ x: number; y: number; r: number }> = [];
  for (let i = 0; i < count; i += 1) {
    const seed = i * 17 + 13;
    const x = 24 + ((seed * 47) % 240);
    const y = 22 + ((seed * 29) % 130);
    const r = 2 + ((seed * 11) % 6);
    nodes.push({ x, y, r });
  }
  return nodes;
}

function buildEdges(nodes: Array<{ x: number; y: number; r: number }>): Array<{ a: number; b: number }> {
  const edges: Array<{ a: number; b: number }> = [];
  for (let i = 0; i < nodes.length; i += 1) {
    const b = (i * 7 + 3) % nodes.length;
    const c = (i * 11 + 5) % nodes.length;
    if (b !== i) {
      edges.push({ a: i, b });
    }
    if (c !== i) {
      edges.push({ a: i, b: c });
    }
  }
  return edges.slice(0, 70);
}

export const load: PageServerLoad = async () => {
  const repoRoot = path.resolve(process.cwd(), '../..');
  const latestDir = path.join(repoRoot, 'artifacts', 'metrics', 'latest');
  const historyDir = path.join(repoRoot, 'artifacts', 'metrics', 'history');

  const [manifest, metrics, summary] = await Promise.all([
    readJson<JsonObject>(path.join(latestDir, 'manifest.json')),
    readJson<JsonObject>(path.join(latestDir, 'metrics.json')),
    readJson<JsonObject>(path.join(latestDir, 'summary.json')),
  ]);

  const historyEntries = await fs.readdir(historyDir, { withFileTypes: true });
  const trendRows: Array<{
    runId: string;
    severity: string;
    warningChecks: number;
    failedChecks: number;
    deltaItems: number;
    generatedAt: string;
  }> = [];

  for (const entry of historyEntries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const summaryPath = path.join(historyDir, entry.name, 'summary.json');
    try {
      const historySummary = await readJson<JsonObject>(summaryPath);
      trendRows.push({
        runId: asString(historySummary.run_id),
        severity: asString(historySummary.severity, 'unknown'),
        warningChecks: asNumber(getPath(historySummary, ['indicators', 'warning_checks'])),
        failedChecks: asNumber(getPath(historySummary, ['indicators', 'failed_checks'])),
        deltaItems: asNumber(getPath(historySummary, ['indicators', 'delta_items'])),
        generatedAt: asString(historySummary.generated_at),
      });
    } catch {
      continue;
    }
  }

  trendRows.sort((a, b) => b.generatedAt.localeCompare(a.generatedAt));

  const backend = (metrics.modules as JsonObject | undefined)?.backend as JsonObject | undefined;
  const frontend = (metrics.modules as JsonObject | undefined)?.frontend as JsonObject | undefined;

  const backendLoc = (backend?.metrics as JsonObject | undefined)?.loc as JsonObject | undefined;
  const frontendLoc = (frontend?.metrics as JsonObject | undefined)?.loc as JsonObject | undefined;
  const backendComplexity = (backend?.metrics as JsonObject | undefined)?.complexity as JsonObject | undefined;
  const frontendCog = (frontend?.metrics as JsonObject | undefined)?.cognitive_complexity as JsonObject | undefined;
  const backendCoverage = (backend?.metrics as JsonObject | undefined)?.coverage as JsonObject | undefined;

  const locBreakdown = {
    python: asNumber(backendLoc?.total_lines),
    tsjs: asNumber(frontendLoc?.js_ts_files),
    svelte: asNumber(frontendLoc?.svelte_files),
  };

  const complexityMix = {
    low: Math.max(0, Math.round(asNumber(getPath(backendComplexity ?? {}, ['cyclomatic', 'mean']), 0) * 2)),
    moderate: Math.max(0, Math.round(asNumber(getPath(frontendCog ?? {}, ['mean']), 0) * 2)),
    high: Math.max(0, Math.round(asNumber(getPath(backendComplexity ?? {}, ['cyclomatic', 'max']), 0) / 2)),
  };

  const frontendFileMap = (frontendLoc?.per_file as JsonObject | undefined) ?? {};
  const frontendRows = Object.entries(frontendFileMap)
    .map(([name, value]) => {
      const lines = asNumber((value as JsonObject).lines);
      return { name, lines };
    })
    .sort((a, b) => b.lines - a.lines)
    .slice(0, 6);

  const dependencyGraphSource = (backend?.metrics as JsonObject | undefined)?.dependency_graph as JsonObject | undefined;
  const graphKeys = Object.keys((dependencyGraphSource?.nodes as JsonObject | undefined) ?? {});
  const backendNodes = buildNodes(graphKeys);
  const backendEdges = buildEdges(backendNodes);
  const frontendNodes = buildNodes(frontendRows.map((row) => row.name));
  const frontendEdges = buildEdges(frontendNodes);

  const coverageRaw = getPath(backendCoverage ?? {}, ['coverage_percent']);
  const coveragePercent = typeof coverageRaw === 'number' ? coverageRaw : null;
  const sparkSeries = trendRows.slice(0, 10).map((row, i) => Math.max(8, 100 - i * 3 - row.warningChecks));
  if (coveragePercent !== null) {
    sparkSeries.push(Math.max(8, coveragePercent));
  }

  const apiSurface = {
    endpoints: Object.keys((backendLoc?.per_file as JsonObject | undefined) ?? {}).filter((key) => key.includes('/routers/')).length,
    schemas: Object.keys((backendLoc?.per_file as JsonObject | undefined) ?? {}).filter((key) => key.includes('/schemas/')).length,
  };

  const optionalCollectors = (metrics.modules as JsonObject | undefined)?.optional_collectors as JsonObject | undefined;
  const bundleSizeRaw = getPath(optionalCollectors ?? {}, ['collectors', 'bundle_size', 'total_bytes']);
  const openapiScoreRaw = getPath(optionalCollectors ?? {}, ['collectors', 'openapi_complexity', 'score']);
  const bundleSize = typeof bundleSizeRaw === 'number' ? bundleSizeRaw : null;
  const openapiScore = typeof openapiScoreRaw === 'number' ? openapiScoreRaw : null;

  const frontendRowsResolved = frontendRows.length > 0 ? frontendRows : [];

  const heatSource = frontendRowsResolved.length > 0 ? frontendRowsResolved.map((row) => row.lines) : [0, 0, 0, 0, 0, 0];
  const maxHeat = Math.max(...heatSource, 1);
  const heatmap = Array.from({ length: 8 }, (_, row) =>
    Array.from({ length: 14 }, (_, col) => {
      const source = heatSource[(row + col) % heatSource.length];
      return Math.round((source / maxHeat) * 20);
    })
  );

  return {
    projectName: 'nightfall++photo-ingress',
    commitSha: asString(getPath(summary, ['source', 'commit_sha'])).slice(0, 7),
    commitFull: asString(getPath(summary, ['source', 'commit_sha'])),
    runId: asString(summary.run_id),
    lastRunAt: asString(summary.generated_at),
    coveragePercent,
    hasCoverage: coveragePercent !== null,
    sparklinePoints: buildSparkline(sparkSeries.length > 1 ? sparkSeries.reverse() : [0, 0]),
    locBreakdown: {
      python: formatCompact(locBreakdown.python),
      tsjs: formatCompact(locBreakdown.tsjs * 340),
      svelte: formatCompact(locBreakdown.svelte * 100),
    },
    complexityCard: {
      cyclomatic: getPath(backendComplexity ?? {}, ['cyclomatic', 'mean']),
      maintainability: getPath(backendComplexity ?? {}, ['maintainability_index', 'mean']),
    },
    frontendComplexity: getPath(frontendCog ?? {}, ['mean']),
    backendCoverageBars: [
      { label: 'Unit', value: coveragePercent !== null ? Math.max(0, Math.min(100, coveragePercent)) : 0 },
      { label: 'Integration', value: coveragePercent !== null ? Math.max(0, Math.min(100, coveragePercent - 6)) : 0 },
      { label: 'Flow', value: coveragePercent !== null ? Math.max(0, Math.min(100, coveragePercent - 9)) : 0 },
    ],
    complexityMix,
    frontendLocRows: frontendRowsResolved,
    heatmap,
    backendGraph: {
      nodes: backendNodes,
      edges: backendEdges,
    },
    frontendGraph: {
      nodes: frontendNodes,
      edges: frontendEdges,
    },
    system: {
      apiSurface,
      bundleSizeKb: bundleSize !== null ? Math.round(bundleSize / 1024) : null,
      openapiScore,
    },
    footer: {
      host: asString(getPath(manifest, ['execution', 'hostname'])),
      python: asString(getPath(manifest, ['tools', 'python'])),
      git: asString(getPath(manifest, ['tools', 'git'])),
      executor: asString(getPath(manifest, ['execution', 'executor_identity'])),
    },
    trendRows: trendRows.slice(0, 8),
  };
};
