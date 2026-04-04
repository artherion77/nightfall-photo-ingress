<script>
  import { onMount } from 'svelte';

  const defaultData = {
    projectName: 'nightfall++photo-ingress',
    commitSha: 'unknown',
    commitFull: 'unknown',
    runId: 'unknown',
    lastRunAt: 'unknown',
    coveragePercent: null,
    hasCoverage: false,
    sparklinePoints: '0,36 180,36',
    locBreakdown: { python: '0', tsjs: '0', svelte: '0' },
    complexityCard: { cyclomatic: null, maintainability: null },
    frontendComplexity: null,
    backendCoverageBars: [
      { label: 'Unit', value: 0 },
      { label: 'Integration', value: 0 },
      { label: 'Flow', value: 0 },
    ],
    complexityMix: { low: 0, moderate: 0, high: 0 },
    frontendLocRows: [],
    heatmap: Array.from({ length: 8 }, () => Array.from({ length: 14 }, () => 0)),
    backendGraph: { nodes: [], edges: [] },
    frontendGraph: { nodes: [], edges: [] },
    system: { apiSurface: { endpoints: 0, schemas: 0 }, bundleSizeKb: null, openapiScore: null },
    footer: { host: 'unknown', python: 'unknown', git: 'unknown', executor: 'unknown' },
    trendRows: [],
    sourceBranch: 'main',
    repoUrl: null,
    repoHeadUrl: null,
    repoCommitUrl: null,
    runMeta: { startedAt: null, finishedAt: null, durationSeconds: null, runId: 'unknown', branch: 'main' },
    versions: { python: null, typescript: null },
  };

  let data = defaultData;
  let complexityTotal = 0;
  let donutParts = [];
  let donut = [];
  let maxFrontendLoc = 1;
  let coverageText = 'N/A';
  let cyclomaticText = 'N/A';
  let maintainabilityText = 'N/A';
  let frontendComplexityText = 'N/A';
  let repoLabel = 'unknown';
  let commitHref = null;
  let footerCommitHref = null;
  let lastRunDisplay = 'unknown';
  let lastRunDetail = '';
  let tsjsLabelDetail = 'TypeScript / JavaScript';
  let pythonLocDetail = 'Python';
  let metricsFolderHref = null;

  onMount(async () => {
    try {
      const response = await fetch('./__data.json', { cache: 'no-store' });
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      data = {
        ...defaultData,
        ...payload,
      };
    } catch {
      data = defaultData;
    }
  });

  $: complexityTotal = data.complexityMix.low + data.complexityMix.moderate + data.complexityMix.high;
  $: donutParts = [
    { key: 'low', label: 'Low', value: data.complexityMix.low, color: '#53b676' },
    { key: 'moderate', label: 'Moderate', value: data.complexityMix.moderate, color: '#f0b443' },
    { key: 'high', label: 'High', value: data.complexityMix.high, color: '#e15f6b' },
  ];

  function arcPath(startAngle, endAngle, radius, inner) {
    const polar = (angle, r) => {
      const a = (angle - 90) * (Math.PI / 180);
      return { x: 150 + r * Math.cos(a), y: 150 + r * Math.sin(a) };
    };
    const startOuter = polar(endAngle, radius);
    const endOuter = polar(startAngle, radius);
    const startInner = polar(startAngle, inner);
    const endInner = polar(endAngle, inner);
    const largeArc = endAngle - startAngle > 180 ? 1 : 0;
    return [
      `M ${startOuter.x} ${startOuter.y}`,
      `A ${radius} ${radius} 0 ${largeArc} 0 ${endOuter.x} ${endOuter.y}`,
      `L ${startInner.x} ${startInner.y}`,
      `A ${inner} ${inner} 0 ${largeArc} 1 ${endInner.x} ${endInner.y}`,
      'Z'
    ].join(' ');
  }

  $: {
    let runningAngle = 0;
    donut = donutParts.map((part) => {
      const span = complexityTotal > 0 ? (part.value / complexityTotal) * 360 : 0;
      const start = runningAngle;
      const end = runningAngle + span;
      runningAngle = end;
      return {
        ...part,
        d: arcPath(start, end, 118, 72),
      };
    });
  }

  $: maxFrontendLoc = Math.max(...data.frontendLocRows.map((row) => row.lines), 1);

  $: coverageText = data.hasCoverage && data.coveragePercent !== null ? `${Math.round(data.coveragePercent)}%` : 'N/A';
  $: cyclomaticText = typeof data.complexityCard.cyclomatic === 'number' ? data.complexityCard.cyclomatic.toFixed(1) : 'N/A';
  $: maintainabilityText = typeof data.complexityCard.maintainability === 'number'
    ? String(Math.round(data.complexityCard.maintainability))
    : 'N/A';
  $: frontendComplexityText = typeof data.frontendComplexity === 'number'
    ? data.frontendComplexity.toFixed(1)
    : 'N/A';

  $: repoLabel = typeof data.repoUrl === 'string' && data.repoUrl
    ? (() => {
      const match = data.repoUrl.match(/^https?:\/\/[^/]+\/(.+?)\/(.+?)\/?$/);
      if (!match) {
        return data.repoUrl.replace(/^https?:\/\//, '');
      }
      const owner = match[1] || 'repo';
      const repo = match[2] || 'unknown';
      const compactRepo = repo.length > 10 ? `${repo.slice(0, 2)}...` : repo;
      return `@${owner}/${compactRepo}`;
    })()
    : 'unknown';

  $: commitHref = data.repoCommitUrl || data.repoHeadUrl || data.repoUrl || null;
  $: footerCommitHref = commitHref;
  $: metricsFolderHref = data.repoHeadUrl ? `${data.repoHeadUrl}/metrics` : null;

  $: {
    if (typeof data.lastRunAt !== 'string' || !data.lastRunAt || data.lastRunAt === 'unknown') {
      lastRunDisplay = 'unknown';
      lastRunDetail = '';
    } else {
      const parsed = new Date(data.lastRunAt);
      if (Number.isNaN(parsed.getTime())) {
        lastRunDisplay = data.lastRunAt;
        lastRunDetail = '';
      } else {
        const weekday = parsed.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' });
        const yyyy = String(parsed.getUTCFullYear());
        const mm = String(parsed.getUTCMonth() + 1).padStart(2, '0');
        const dd = String(parsed.getUTCDate()).padStart(2, '0');
        const hh = String(parsed.getUTCHours()).padStart(2, '0');
        const min = String(parsed.getUTCMinutes()).padStart(2, '0');
        lastRunDisplay = `${weekday}, ${yyyy}-${mm}-${dd} ${hh}:${min} UTC`;

        const parts = [];
        parts.push(`Run: ${data.runId}`);
        parts.push(`Branch: ${data.sourceBranch}`);
        if (data.commitFull && data.commitFull !== 'unknown') {
          parts.push(`Commit: ${data.commitFull}`);
        }
        if (data.runMeta?.durationSeconds !== null && data.runMeta?.durationSeconds !== undefined) {
          parts.push(`Duration: ${Number(data.runMeta.durationSeconds).toFixed(2)}s`);
        }
        if (data.footer?.host) {
          parts.push(`Host: ${data.footer.host}`);
        }
        if (data.footer?.executor) {
          parts.push(`Executor: ${data.footer.executor}`);
        }
        if (data.footer?.git) {
          parts.push(data.footer.git);
        }
        if (data.footer?.python && data.footer.python !== 'unknown') {
          parts.push(`Python: ${data.footer.python}`);
        }
        lastRunDetail = parts.join(' | ');
      }
    }
  }

  $: {
    tsjsLabelDetail = 'TypeScript / JavaScript';
    if (data.versions?.typescript) {
      tsjsLabelDetail = `${tsjsLabelDetail} (TypeScript ${data.versions.typescript})`;
    }
  }

  $: {
    pythonLocDetail = 'Python';
    if (data.versions?.python) {
      const cleaned = String(data.versions.python).replace(/^Python\s+/i, '').trim();
      pythonLocDetail = cleaned ? `Python ${cleaned}` : 'Python';
    }
  }

  function heatColor(value) {
    if (value >= 18) return '#cc3f38';
    if (value >= 14) return '#db7b2a';
    if (value >= 10) return '#d8b33f';
    if (value >= 6) return '#9ebf3e';
    return '#4a8f4b';
  }
</script>

<svelte:head>
  <title>Code Quality &amp; Metrics Dashboard</title>
</svelte:head>

<div class="page-bg">
  <main class="dashboard">
    <header class="topbar card">
      <div class="brand">
        <span class="brand-mark"></span>
        <h1>{data.projectName} <span class="subtitle">- Code Quality &amp; Metrics Dashboard</span></h1>
      </div>
      <div class="meta-stack">
        {#if commitHref}
          <a class="meta-pill meta-link tip-anchor" href={commitHref} target="_blank" rel="noreferrer" aria-label="Open repository commit">
            <span>Commit: {data.commitSha}</span>
            <span>Repo: {repoLabel}</span>
            <span class="tip-bubble">Opens source commit for this metrics run. {#if data.repoHeadUrl}Head: {data.repoHeadUrl}{/if}</span>
          </a>
        {:else}
          <div class="meta-pill">
            <span>Commit: {data.commitSha}</span>
            <span>Repo: {repoLabel}</span>
          </div>
        {/if}
        <div class="meta-pill tip-anchor" tabindex="0" role="button" aria-label="Show run metadata">
          <span>Last Run:</span>
          <span>{lastRunDisplay}</span>
          {#if lastRunDetail}
            <span class="tip-bubble">{lastRunDetail}</span>
          {/if}
        </div>
      </div>
    </header>

    <section class="cards-row">
      <article class="card metric-card">
        <h2>Python Test Coverage</h2>
        <div class="hero-value">{coverageText}</div>
        <svg viewBox="0 0 180 42" aria-label="Coverage sparkline" class="sparkline">
          <polyline points={data.sparklinePoints} fill="none" stroke="#9bf77a" stroke-width="2.5" stroke-linecap="round" />
        </svg>
      </article>

      <article class="card metric-card">
        <h2>LOC Breakdown</h2>
        <dl class="kv">
          <div>
            <dt><span class="tip-anchor">
              Python
              <span class="tip-bubble">{pythonLocDetail}</span>
            </span></dt>
            <dd>{data.locBreakdown.python}</dd>
          </div>
          <div>
            <dt><span class="tip-anchor">
              TS / JS
              <span class="tip-bubble">{tsjsLabelDetail}</span>
            </span></dt>
            <dd>{data.locBreakdown.tsjs}</dd>
          </div>
          <div>
            <dt>
              <a class="tip-anchor loc-link" href="https://www.svelte.dev" target="_blank" rel="noreferrer" aria-label="Open Svelte website">
                Svelte
                <span class="tip-bubble">https://svelte.dev. web development for the rest of us</span>
              </a>
            </dt>
            <dd>{data.locBreakdown.svelte}</dd>
          </div>
        </dl>
      </article>

      <article class="card metric-card">
        <h2>Python Complexity</h2>
        <dl class="kv">
          <div><dt>Cyclomatic</dt><dd>{cyclomaticText}</dd></div>
          <div><dt>Maintainability</dt><dd>{maintainabilityText}</dd></div>
        </dl>
      </article>

      <article class="card metric-card">
        <h2>Frontend Cognitive Complexity <span class="tip-anchor hint-inline" tabindex="0" role="button" aria-label="Complexity metric explanation">i<span class="tip-bubble">Heuristic score from frontend_collector: branching tokens weighted by nesting depth. Typical human-maintained app range: 12-40 mean. Lower is easier to maintain.</span></span></h2>
        <div class="hero-value compact"><strong>{frontendComplexityText}</strong></div>
      </article>
    </section>

    <section class="section-block">
      <h3>Backend Metrics</h3>
      <div class="grid-three">
        <article class="card panel">
          <h4>Coverage Breakdown</h4>
          {#if !data.hasCoverage}
            <p class="na-note">Coverage collector unavailable in latest artifact.</p>
          {/if}
          <svg viewBox="0 0 320 220" class="chart">
            {#each data.backendCoverageBars as bar, idx}
              {@const suitePath = idx === 0 ? 'tests/unit' : idx === 1 ? 'tests/integration' : 'testspecs'}
              {@const suiteHref = data.repoHeadUrl ? `${data.repoHeadUrl}/${suitePath}` : null}
              <g transform={`translate(${48 + idx * 88}, 20)`}>
                <rect x="0" y={170 - bar.value * 1.45} width="44" height={bar.value * 1.45} rx="3" fill={`url(#barGrad${idx})`} />
                <text x="22" y="194" text-anchor="middle" class="axis-label">{bar.label}</text>
                <text x="22" y={164 - bar.value * 1.45} text-anchor="middle" class="value-label">{Math.round(bar.value)}%</text>
                <defs>
                  <linearGradient id={`barGrad${idx}`} x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stop-color={idx === 0 ? '#3f90ff' : idx === 1 ? '#58bd55' : '#8ccd62'} />
                    <stop offset="100%" stop-color="#1f2e4f" />
                  </linearGradient>
                </defs>
              </g>
              <foreignObject x={32 + idx * 88} y="24" width="84" height="160">
                <div xmlns="http://www.w3.org/1999/xhtml" class="bar-hover tip-anchor" tabindex="0" role="button" aria-label={`Coverage details for ${bar.label}`}>
                  <span class="tip-bubble">
                    {bar.label}: {bar.value.toFixed(1)}%<br />
                    Source: pytest-cov aggregate<br />
                    Suite path: {suitePath}
                    {#if suiteHref}
                      <br />
                      <a href={suiteHref} target="_blank" rel="noreferrer">Open in repo</a>
                    {/if}
                  </span>
                </div>
              </foreignObject>
            {/each}
          </svg>
        </article>

        <article class="card panel">
          <h4>Complexity Distribution</h4>
          <svg viewBox="0 0 300 300" class="chart donut-chart">
            {#each donut as segment}
              <path d={segment.d} fill={segment.color}></path>
            {/each}
          </svg>
          <div class="legend">
            {#each donutParts as part}
              <span><i style={`background:${part.color}`}></i>{part.label}</span>
            {/each}
          </div>
        </article>

        <article class="card panel">
          <h4>Dependency Graph</h4>
          <svg viewBox="0 0 300 180" class="chart graph">
            {#each data.backendGraph.edges as edge}
              <line
                x1={data.backendGraph.nodes[edge.a].x}
                y1={data.backendGraph.nodes[edge.a].y}
                x2={data.backendGraph.nodes[edge.b].x}
                y2={data.backendGraph.nodes[edge.b].y}
                stroke="#70819f"
                stroke-opacity="0.32"
              />
            {/each}
            {#each data.backendGraph.nodes as node}
              <circle cx={node.x} cy={node.y} r={node.r} fill="#cfd9ea" fill-opacity="0.78" />
            {/each}
          </svg>
        </article>
      </div>
    </section>

    <section class="section-block">
      <h3>Frontend Metrics</h3>
      <div class="grid-three">
        <article class="card panel">
          <h4>LOC per Component</h4>
          {#if data.frontendLocRows.length === 0}
            <p class="na-note">No frontend per-file LOC emitted in latest artifact.</p>
          {/if}
          <div class="loc-bars">
            {#each data.frontendLocRows as row}
              {@const pctOfMax = maxFrontendLoc > 0 ? (row.lines / maxFrontendLoc) * 100 : 0}
              {@const pathParts = row.name.split('/')}
              {@const fileName = pathParts.at(-1) || row.name}
              {@const parentPath = pathParts.length > 1 ? pathParts.slice(0, -1).join('/') : '(root)'}
              <div class="loc-row tip-anchor" tabindex="0" role="button" aria-label="Show LOC row details">
                <span>{row.name.split('/').at(-1)}</span>
                <div class="bar"><i style={`width:${(row.lines / maxFrontendLoc) * 100}%`}></i></div>
                <span class="tip-bubble loc-tip">Filename: {fileName}<br />Path: {parentPath}<br />LOC: {row.lines}<br />Bar share: {pctOfMax.toFixed(1)}%</span>
              </div>
            {/each}
          </div>
        </article>

        <article class="card panel">
          <h4>Cognitive Complexity</h4>
          <div class="heatmap">
            {#each data.heatmap as line}
              <div class="heat-row">
                {#each line as value}
                  <span style={`background:${heatColor(value)}`}></span>
                {/each}
              </div>
            {/each}
          </div>
        </article>

        <article class="card panel">
          <h4>JS Dependency Graph</h4>
          <svg viewBox="0 0 300 180" class="chart graph">
            {#each data.frontendGraph.edges as edge}
              <line
                x1={data.frontendGraph.nodes[edge.a].x}
                y1={data.frontendGraph.nodes[edge.a].y}
                x2={data.frontendGraph.nodes[edge.b].x}
                y2={data.frontendGraph.nodes[edge.b].y}
                stroke="#7d8cac"
                stroke-opacity="0.31"
              />
            {/each}
            {#each data.frontendGraph.nodes as node}
              <circle cx={node.x} cy={node.y} r={node.r} fill="#dce6f5" fill-opacity="0.8" />
            {/each}
          </svg>
        </article>
      </div>
    </section>

    <section class="section-block">
      <h3>System Metrics</h3>
      <div class="grid-three">
        <article class="card panel">
          <h4>API Surface</h4>
          <dl class="kv wide">
            <div><dt>Endpoints</dt><dd>{data.system.apiSurface.endpoints}</dd></div>
            <div><dt>Schemas</dt><dd>{data.system.apiSurface.schemas}</dd></div>
          </dl>
        </article>

        <article class="card panel">
          <h4>Bundle Size</h4>
          <div class="hero-value compact"><strong>{data.system.bundleSizeKb !== null ? `${data.system.bundleSizeKb} KB` : 'N/A'}</strong></div>
        </article>

        <article class="card panel">
          <h4>OpenAPI Complexity</h4>
          <div class="hero-value compact">Complexity Score: <strong>{data.system.openapiScore !== null ? data.system.openapiScore : 'N/A'}</strong></div>
        </article>
      </div>
    </section>

    <footer class="footer card">
      {#if footerCommitHref}
        <a class="tip-anchor footer-link" href={footerCommitHref} target="_blank" rel="noreferrer" aria-label="Open commit">
          <span>{data.commitSha} on {data.footer.host}</span>
          <span class="tip-bubble">Open source commit {data.commitFull}</span>
        </a>
      {:else}
        <span>{data.commitSha} on {data.footer.host}</span>
      {/if}
      <span>{data.footer.python}</span>
      <span>{data.footer.git}</span>
      <span>executor {data.footer.executor}</span>
      <span class="footer-credit">
        {#if metricsFolderHref}
          <a class="footer-inline-link" href={metricsFolderHref} target="_blank" rel="noreferrer">metrrics runner on {data.footer.host}</a>, created by
        {:else}
          metrrics runner on {data.footer.host}, created by
        {/if}
        <a class="footer-inline-link" href="https://github.com/copilot/" target="_blank" rel="noreferrer">GitHub CoPilot</a>
      </span>
    </footer>
  </main>
</div>
