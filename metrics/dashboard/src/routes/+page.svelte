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
    locTotal: '0',
    locDetail: { total: 0, purpose: { production: 0, test: 0, other: 0 }, technology: { python: 0, svelte: 0, jsts: 0, bash: 0, other: 0 }, totalFiles: 0, note: '' },
    complexityCard: {
      cyclomatic: null,
      maintainability: null,
      frontend: { value: null, source: null, status: null, parser_version_label: null },
    },
    frontendComplexity: null,
    backendCoverageBars: [
      { label: 'Unit', value: 0 },
      { label: 'Integration', value: 0 },
      { label: 'Flow', value: 0 },
    ],
    complexityMix: { low: 0, moderate: 0, high: 0 },
    complexityBreakdownDetail: {
      high: { category: 'high', totalModules: 0, topModules: [] },
      moderate: { category: 'moderate', totalModules: 0, topModules: [] },
      low: { category: 'low', totalModules: 0, topModules: [] },
    },
    frontendLocRows: [],
    heatmap: Array.from({ length: 8 }, () => Array.from({ length: 14 }, () => 0)),
    backendGraph: { nodes: [], edges: [], nodeDetails: [] },
    frontendGraph: { nodes: [], edges: [], nodeDetails: [] },
    pythonComplexityReference: {
      cyclomatic: { method: 'McCabe cyclomatic complexity via radon', scale: { min: 1, max: 20 }, industryMedian: 4.5 },
      maintainability: { method: 'Maintainability Index via radon', scale: { min: 0, max: 100 }, industryMedian: 65 },
    },
    frontendComplexityReference: {
      method: 'Sonar Cognitive Complexity (tree-sitter AST; nesting-penalised increments)',
      scale: { min: 0, max: 60 },
      industryMedian: 26,
      industryMeanRange: { min: 12, max: 40 },
    },
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
  let metricsFolderHref = null;
  let purposeDonut = [];
  let techDonut = [];
  let cyclomaticProjectPct = 0;
  let cyclomaticMedianPct = 0;
  let maintainabilityProjectPct = 0;
  let maintainabilityMedianPct = 0;
  let frontendProjectPct = 0;
  let frontendIndustryMeanPct = 0;
  let cyclomaticRelation = 'near median';
  let maintainabilityRelation = 'near median';
  let frontendRelation = 'near industry mean';
  let cyclomaticProjectColor = '#4a8f4b';
  let cyclomaticMedianColor = '#d8b33f';
  let maintainabilityProjectColor = '#4a8f4b';
  let maintainabilityMedianColor = '#d8b33f';
  let frontendProjectColor = '#4a8f4b';
  let activeComplexitySegment = null;
  let complexityTotalModules = 0;
  let backendNodeHover = null;
  let frontendNodeHover = null;

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

  function heatColor(value) {
    if (value >= 18) return '#cc3f38';
    if (value >= 14) return '#db7b2a';
    if (value >= 10) return '#d8b33f';
    if (value >= 6) return '#9ebf3e';
    return '#4a8f4b';
  }

  function metricToScalePercent(value, min, max) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return 0;
    }
    const span = Math.max(1, max - min);
    const clamped = Math.min(max, Math.max(min, value));
    return ((clamped - min) / span) * 100;
  }

  function classifyAgainstMedian(value, median) {
    if (typeof value !== 'number' || !Number.isFinite(value) || !Number.isFinite(median)) {
      return 'near median';
    }
    const threshold = Math.max(0.5, Math.abs(median) * 0.1);
    if (value < median - threshold) return 'below median';
    if (value > median + threshold) return 'above median';
    return 'near median';
  }

  function classifyAgainstMean(value, mean) {
    if (typeof value !== 'number' || !Number.isFinite(value) || !Number.isFinite(mean)) {
      return 'near industry mean';
    }
    const threshold = Math.max(0.5, Math.abs(mean) * 0.1);
    if (value < mean - threshold) return 'below industry mean';
    if (value > mean + threshold) return 'above industry mean';
    return 'near industry mean';
  }

  function cyclomaticGradientColor(pct) {
    if (pct < 33) return '#4a8f4b';
    if (pct < 66) return '#d8b33f';
    return '#cc3f38';
  }

  function maintainabilityGradientColor(pct) {
    if (pct < 33) return '#cc3f38';
    if (pct < 66) return '#d8b33f';
    return '#4a8f4b';
  }

  function graphNodeTooltip(detail, graphType) {
    if (!detail) {
      return `Module: unknown\nType: ${graphType}\nFan-in/Fan-out: n/a\nCycle: n/a`;
    }
    const modulePath = detail.path || detail.module || 'unknown';
    const fanIn = typeof detail.fan_in === 'number' ? detail.fan_in : 'n/a';
    const fanOut = typeof detail.fan_out === 'number' ? detail.fan_out : 'n/a';
    const cycle = detail.in_cycle ? 'yes' : 'no';
    return `Module: ${modulePath}\nType: ${graphType}\nFan-in: ${fanIn} / Fan-out: ${fanOut}\nCycle: ${cycle}`;
  }

  $: {
    const cycloRef = data.pythonComplexityReference?.cyclomatic || { scale: { min: 1, max: 20 }, industryMedian: 4.5 };
    const cycloMin = Number(cycloRef.scale?.min ?? 1);
    const cycloMax = Number(cycloRef.scale?.max ?? 20);
    const cycloMedian = Number(cycloRef.median ?? cycloRef.industryMedian ?? 4.5);
    cyclomaticProjectPct = metricToScalePercent(data.complexityCard?.cyclomatic, cycloMin, cycloMax);
    cyclomaticMedianPct = metricToScalePercent(cycloMedian, cycloMin, cycloMax);
    cyclomaticRelation = classifyAgainstMedian(data.complexityCard?.cyclomatic, cycloMedian);
    cyclomaticProjectColor = cyclomaticGradientColor(cyclomaticProjectPct);
    cyclomaticMedianColor = cyclomaticGradientColor(cyclomaticMedianPct);

    const miRef = data.pythonComplexityReference?.maintainability || { scale: { min: 0, max: 100 }, industryMedian: 65 };
    const miMin = Number(miRef.scale?.min ?? 0);
    const miMax = Number(miRef.scale?.max ?? 100);
    const miMedian = Number(miRef.median ?? miRef.industryMedian ?? 65);
    maintainabilityProjectPct = metricToScalePercent(data.complexityCard?.maintainability, miMin, miMax);
    maintainabilityMedianPct = metricToScalePercent(miMedian, miMin, miMax);
    maintainabilityRelation = classifyAgainstMedian(data.complexityCard?.maintainability, miMedian);
    maintainabilityProjectColor = maintainabilityGradientColor(maintainabilityProjectPct);
    maintainabilityMedianColor = maintainabilityGradientColor(maintainabilityMedianPct);

    const frontendRef = data.frontendComplexityReference || {
      scale: { min: 0, max: 60 },
      industryMedian: 5,
    };
    const frontendMin = Number(frontendRef.scale?.min ?? 0);
    const frontendMax = Number(frontendRef.scale?.max ?? 60);
    const frontendIndustryMean = 5.0;
    frontendProjectPct = metricToScalePercent(data.frontendComplexity, frontendMin, frontendMax);
    frontendIndustryMeanPct = metricToScalePercent(frontendIndustryMean, frontendMin, frontendMax);
    frontendRelation = classifyAgainstMean(data.frontendComplexity, frontendIndustryMean);
    frontendProjectColor = cyclomaticGradientColor(frontendProjectPct);

    const detail = data.complexityBreakdownDetail || {};
    complexityTotalModules = Number(detail.high?.totalModules || 0)
      + Number(detail.moderate?.totalModules || 0)
      + Number(detail.low?.totalModules || 0);
  }

  $: {
    const _pt = data.locDetail?.purpose || { production: 0, test: 0, other: 0 };
    const _ptTotal = (_pt.production || 0) + (_pt.test || 0) + (_pt.other || 0);
    const _purposeParts = [
      { label: 'Production', value: _pt.production || 0, color: '#53b676' },
      { label: 'Test', value: _pt.test || 0, color: '#3f90ff' },
      { label: 'Other', value: _pt.other || 0, color: '#8a8fa8' },
    ];
    let _pAngle = 0;
    purposeDonut = _purposeParts.map((p) => {
      const span = _ptTotal > 0 ? (p.value / _ptTotal) * 360 : 0;
      const pct = _ptTotal > 0 ? Math.round((p.value / _ptTotal) * 100) : 0;
      const d = span >= 1.8 ? arcPath(_pAngle, _pAngle + span, 40, 22) : '';
      _pAngle += span;
      return { ...p, d, pct };
    }).filter((p) => p.d !== '');
  }

  $: {
    const _tm = data.locDetail?.technology || { python: 0, svelte: 0, jsts: 0, bash: 0, other: 0 };
    const _tmTotal = Object.values(_tm).reduce((acc, v) => acc + (Number(v) || 0), 0);
    const _techParts = [
      { label: 'Python', value: _tm.python || 0, color: '#4584e0' },
      { label: 'Svelte', value: _tm.svelte || 0, color: '#ff6900' },
      { label: 'JS/TS', value: _tm.jsts || 0, color: '#f0b443' },
      { label: 'Bash', value: _tm.bash || 0, color: '#9b7fe8' },
      { label: 'Other', value: _tm.other || 0, color: '#8a8fa8' },
    ];
    let _tAngle = 0;
    techDonut = _techParts.map((p) => {
      const span = _tmTotal > 0 ? (p.value / _tmTotal) * 360 : 0;
      const pct = _tmTotal > 0 ? Math.round((p.value / _tmTotal) * 100) : 0;
      const d = span >= 1.8 ? arcPath(_tAngle, _tAngle + span, 40, 22) : '';
      _tAngle += span;
      return { ...p, d, pct };
    }).filter((p) => p.d !== '');
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
        <h2>Python Test Coverage <span class="tip-anchor hint-inline" tabindex="0" role="button" aria-label="Coverage sparkline source details">i<span class="tip-bubble">Measured via pytest + pytest-cov with coverage.py aggregation (unit suite baseline).<br />Coverage ranking hint:<br />50-60%: risky / weak<br />60-70%: industry median<br />70-80%: good<br />80-90%: very good<br />&gt;90%: exceptional / library-grade</span></span></h2>
        <div class="hero-value">{coverageText}</div>
        <svg viewBox="0 0 180 42" aria-label="Coverage sparkline" class="sparkline">
          <polyline points={data.sparklinePoints} fill="none" stroke="#9bf77a" stroke-width="2.5" stroke-linecap="round" />
        </svg>
      </article>

      <article class="card metric-card">
        <h2>Total Lines of Code</h2>
        <div class="hero-value tip-anchor" tabindex="0" role="button" aria-label="Show LOC breakdown">
          <strong>{data.locTotal}</strong>
          <div class="tip-bubble loc-detail-tip">
            <div class="loc-tip-charts">
              <div class="loc-tip-chart">
                <strong>Purpose</strong>
                <svg viewBox="0 0 100 100" class="tip-donut" aria-hidden="true">
                  {#each purposeDonut as seg}
                    <path d={seg.d} fill={seg.color} transform="translate(-100,-100)" />
                  {/each}
                </svg>
                <div class="tip-mini-legend">
                  {#each purposeDonut as seg}
                    <span><i style={`background:${seg.color}`}></i>{seg.label} {seg.pct}%</span>
                  {/each}
                </div>
              </div>
              <div class="loc-tip-chart">
                <strong>Technology</strong>
                <svg viewBox="0 0 100 100" class="tip-donut" aria-hidden="true">
                  {#each techDonut as seg}
                    <path d={seg.d} fill={seg.color} transform="translate(-100,-100)" />
                  {/each}
                </svg>
                <div class="tip-mini-legend">
                  {#each techDonut as seg}
                    <span><i style={`background:${seg.color}`}></i>{seg.label} {seg.pct}%</span>
                  {/each}
                </div>
              </div>
            </div>
            <p class="tip-note">{data.locDetail?.note || ''}</p>
            <p class="tip-note">{data.locDetail?.totalFiles || 0} files counted.</p>
          </div>
        </div>
      </article>

      <article class="card metric-card">
        <h2>Complexity</h2>
        <dl class="kv kv-compact">
          <div>
            <dt>
              <span class="tip-anchor">
                Web Frontend<br>Cognitive
                <span class="tip-bubble scale-tip">
                  <strong>{data.frontendComplexityReference.method}</strong><br />
                  Scale: {data.frontendComplexityReference.scale.min}-{data.frontendComplexityReference.scale.max} (lower is simpler).<br />
                  Per-file industry mean (typical frontend, JS/TS/Svelte): 5.0
                  {#if data.complexityCard?.frontend?.source}<br />Source: {data.complexityCard.frontend.source}{/if}
                  {#if data.complexityCard?.frontend?.status}<br />Status: {data.complexityCard.frontend.status}{/if}
                  {#if data.complexityCard?.frontend?.parser_version_label}<br />Parser: {data.complexityCard.frontend.parser_version_label}{/if}
                  <br />Classification: {frontendRelation}
                  <span class="scale-bar cyclomatic">
                    <span class="marker project" style={`left:${frontendProjectPct}%; border-top-color:${frontendProjectColor};`}></span>
                    <span class="marker median" style={`left:${frontendIndustryMeanPct}%;`}></span>
                  </span>
                  <span class="scale-legend">▼ Project value &nbsp; ▲ Industry mean</span>
                </span>
              </span>
            </dt>
            <dd>{frontendComplexityText}</dd>
          </div>
          <div>
            <dt>
              <span class="tip-anchor">
                Backend<br>Cyclomatic
                <span class="tip-bubble scale-tip">
                  <strong>Cyclomatic Complexity (McCabe via radon)</strong><br />
                  Scale: {data.pythonComplexityReference.cyclomatic.scale.min}-{data.pythonComplexityReference.cyclomatic.scale.max} (lower is simpler).<br />
                  Industry median (typical Python projects): {data.pythonComplexityReference.cyclomatic.industryMedian}
                  <br />Classification: {cyclomaticRelation}
                  <span class="scale-bar cyclomatic">
                    <span class="marker project" style={`left:${cyclomaticProjectPct}%; border-bottom-color:${cyclomaticProjectColor};`}></span>
                    <span class="marker median" style={`left:${cyclomaticMedianPct}%; border-bottom-color:${cyclomaticMedianColor};`}></span>
                  </span>
                  <span class="scale-legend">▼ Project value &nbsp; ▲ Industry median</span>
                </span>
              </span>
            </dt>
            <dd>{cyclomaticText}</dd>
          </div>
          <div>
            <dt>
              <span class="tip-anchor">
                Backend<br>Maintainability
                <span class="tip-bubble scale-tip">
                  <strong>Maintainability Index (radon)</strong><br />
                  Scale: {data.pythonComplexityReference.maintainability.scale.min}-{data.pythonComplexityReference.maintainability.scale.max} (higher is better).<br />
                  Industry median (typical Python projects): {data.pythonComplexityReference.maintainability.industryMedian}
                  <br />Classification: {maintainabilityRelation}
                  <span class="scale-bar maintainability">
                    <span class="marker project" style={`left:${maintainabilityProjectPct}%; border-bottom-color:${maintainabilityProjectColor};`}></span>
                    <span class="marker median" style={`left:${maintainabilityMedianPct}%; border-bottom-color:${maintainabilityMedianColor};`}></span>
                  </span>
                  <span class="scale-legend">▼ Project value &nbsp; ▲ Industry median</span>
                </span>
              </span>
            </dt>
            <dd>{maintainabilityText}</dd>
          </div>
        </dl>
      </article>

      <article class="card metric-card"></article>
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
                    Source: {idx === 0 ? 'pytest-cov aggregate (measured)' : 'derived from measured unit coverage (synthetic)'}<br />
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

        <article class="card panel panel-has-overlay">
          <h4>Complexity Breakdown</h4>
          <p class="panel-subtle">{complexityTotalModules} modules</p>
          <svg viewBox="0 0 300 300" class="chart donut-chart">
            {#each donut as segment}
              <path
                d={segment.d}
                fill={segment.color}
                class="donut-segment"
                role="button"
                aria-label={`Show ${segment.label} complexity breakdown details`}
                on:mouseenter={() => (activeComplexitySegment = segment.key)}
                on:mouseleave={() => (activeComplexitySegment = null)}
                on:focus={() => (activeComplexitySegment = segment.key)}
                on:blur={() => (activeComplexitySegment = null)}
                tabindex="0"
              ></path>
            {/each}
          </svg>
          <div class="legend">
            {#each donutParts as part}
              <span
                class="legend-item"
                role="button"
                aria-label={`Show ${part.label} complexity breakdown details`}
                on:mouseenter={() => (activeComplexitySegment = part.key)}
                on:mouseleave={() => (activeComplexitySegment = null)}
                on:focus={() => (activeComplexitySegment = part.key)}
                on:blur={() => (activeComplexitySegment = null)}
                tabindex="0"
              ><i style={`background:${part.color}`}></i>{part.label}</span>
            {/each}
          </div>
          {#if activeComplexitySegment}
            {@const detail = data.complexityBreakdownDetail?.[activeComplexitySegment] || { totalModules: 0, topModules: [] }}
            <div class="segment-tip-panel">
              <strong>Top 10 / {detail.totalModules} modules contributing to {activeComplexitySegment} complexity</strong>
              <div class="tip-section">
                {#if detail.topModules.length === 0}
                  <div>None</div>
                {:else}
                  {#each detail.topModules as mod}
                    <div>{mod.module} ({mod.type}, {mod.score})</div>
                  {/each}
                {/if}
              </div>
            </div>
          {/if}
        </article>

        <article class="card panel">
          <h4>Dependency Graph</h4>
          <div class="graph-wrap">
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
              {#each data.backendGraph.nodes as node, idx}
                {@const nodeDetail = data.backendGraph.nodeDetails?.[idx]}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.r}
                  fill="#cfd9ea"
                  fill-opacity="0.78"
                  class="graph-node"
                  role="button"
                  aria-label={`Show backend dependency node details for ${(nodeDetail?.path || 'unknown')}`}
                  on:mouseenter={() => (backendNodeHover = nodeDetail || { path: 'unknown', fan_in: 'n/a', fan_out: 'n/a', in_cycle: false })}
                  on:mouseleave={() => (backendNodeHover = null)}
                  on:focus={() => (backendNodeHover = nodeDetail || { path: 'unknown', fan_in: 'n/a', fan_out: 'n/a', in_cycle: false })}
                  on:blur={() => (backendNodeHover = null)}
                  tabindex="0"
                />
              {/each}
            </svg>
            {#if backendNodeHover}
              <div class="graph-node-tip">
                <div>Module: {backendNodeHover.path || 'unknown'}</div>
                <div>Type: backend</div>
                <div>Fan-in / Fan-out: {backendNodeHover.fan_in ?? 'n/a'} / {backendNodeHover.fan_out ?? 'n/a'}</div>
                <div>Cycle: {backendNodeHover.in_cycle ? 'yes' : 'no'}</div>
              </div>
            {/if}
          </div>
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
          <div class="graph-wrap">
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
              {#each data.frontendGraph.nodes as node, idx}
                {@const nodeDetail = data.frontendGraph.nodeDetails?.[idx]}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.r}
                  fill="#dce6f5"
                  fill-opacity="0.8"
                  class="graph-node"
                  role="button"
                  aria-label={`Show frontend dependency node details for ${(nodeDetail?.path || 'unknown')}`}
                  on:mouseenter={() => (frontendNodeHover = nodeDetail || { path: 'unknown', fan_in: 'n/a', fan_out: 'n/a', in_cycle: false })}
                  on:mouseleave={() => (frontendNodeHover = null)}
                  on:focus={() => (frontendNodeHover = nodeDetail || { path: 'unknown', fan_in: 'n/a', fan_out: 'n/a', in_cycle: false })}
                  on:blur={() => (frontendNodeHover = null)}
                  tabindex="0"
                />
              {/each}
            </svg>
            {#if frontendNodeHover}
              <div class="graph-node-tip">
                <div>Module: {frontendNodeHover.path || 'unknown'}</div>
                <div>Type: frontend</div>
                <div>Fan-in / Fan-out: {frontendNodeHover.fan_in ?? 'n/a'} / {frontendNodeHover.fan_out ?? 'n/a'}</div>
                <div>Cycle: {frontendNodeHover.in_cycle ? 'yes' : 'no'}</div>
              </div>
            {/if}
          </div>
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
