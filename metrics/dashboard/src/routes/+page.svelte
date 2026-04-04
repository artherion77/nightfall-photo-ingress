<script lang="ts">
  export let data: {
    projectName: string;
    commitSha: string;
    commitFull: string;
    runId: string;
    lastRunAt: string;
    coveragePercent: number | null;
    hasCoverage: boolean;
    sparklinePoints: string;
    locBreakdown: { python: string; tsjs: string; svelte: string };
    complexityCard: { cyclomatic: unknown; maintainability: unknown };
    frontendComplexity: unknown;
    backendCoverageBars: Array<{ label: string; value: number }>;
    complexityMix: { low: number; moderate: number; high: number };
    frontendLocRows: Array<{ name: string; lines: number }>;
    heatmap: number[][];
    backendGraph: { nodes: Array<{ x: number; y: number; r: number }>; edges: Array<{ a: number; b: number }> };
    frontendGraph: { nodes: Array<{ x: number; y: number; r: number }>; edges: Array<{ a: number; b: number }> };
    system: { apiSurface: { endpoints: number; schemas: number }; bundleSizeKb: number | null; openapiScore: number | null };
    footer: { host: string; python: string; git: string; executor: string };
    trendRows: Array<{ runId: string; severity: string; warningChecks: number; failedChecks: number; deltaItems: number; generatedAt: string }>;
  };

  const complexityTotal = data.complexityMix.low + data.complexityMix.moderate + data.complexityMix.high;
  const donutParts = [
    { key: 'low', label: 'Low', value: data.complexityMix.low, color: '#53b676' },
    { key: 'moderate', label: 'Moderate', value: data.complexityMix.moderate, color: '#f0b443' },
    { key: 'high', label: 'High', value: data.complexityMix.high, color: '#e15f6b' },
  ];

  function arcPath(startAngle: number, endAngle: number, radius: number, inner: number): string {
    const polar = (angle: number, r: number) => {
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

  let runningAngle = 0;
  const donut = donutParts.map((part) => {
    const span = complexityTotal > 0 ? (part.value / complexityTotal) * 360 : 0;
    const start = runningAngle;
    const end = runningAngle + span;
    runningAngle = end;
    return {
      ...part,
      d: arcPath(start, end, 118, 72),
    };
  });

  const maxFrontendLoc = Math.max(...data.frontendLocRows.map((row) => row.lines), 1);

  const coverageText = data.hasCoverage && data.coveragePercent !== null ? `${Math.round(data.coveragePercent)}%` : 'N/A';
  const cyclomaticText = typeof data.complexityCard.cyclomatic === 'number' ? data.complexityCard.cyclomatic.toFixed(1) : 'N/A';
  const maintainabilityText = typeof data.complexityCard.maintainability === 'number'
    ? String(Math.round(data.complexityCard.maintainability))
    : 'N/A';
  const frontendComplexityText = typeof data.frontendComplexity === 'number'
    ? data.frontendComplexity.toFixed(1)
    : 'N/A';

  function heatColor(value: number): string {
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
        <div class="meta-pill">Commit: {data.commitSha}</div>
        <div class="meta-pill">Last Run: {data.lastRunAt}</div>
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
          <div><dt>Python</dt><dd>{data.locBreakdown.python}</dd></div>
          <div><dt>TS / JS</dt><dd>{data.locBreakdown.tsjs}</dd></div>
          <div><dt>Svelte</dt><dd>{data.locBreakdown.svelte}</dd></div>
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
        <h2>Frontend Cognitive Complexity</h2>
        <div class="hero-value compact">ESLint / SonarJS: <strong>{frontendComplexityText}</strong></div>
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
              <div class="loc-row">
                <span>{row.name.split('/').at(-1)}</span>
                <div class="bar"><i style={`width:${(row.lines / maxFrontendLoc) * 100}%`}></i></div>
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
      <span>{data.commitSha} on {data.footer.host}</span>
      <span>Python {data.footer.python}</span>
      <span>{data.footer.git}</span>
      <span>executor {data.footer.executor}</span>
    </footer>
  </main>
</div>
