<script lang="ts">
  interface PollHistoryEntry {
    day: string;
    duration_s: number;
  }

  interface Props {
    history?: PollHistoryEntry[];
  }

  let { history = [] }: Props = $props();

  // SVG viewport constants
  const CHART_W = 320;
  const CHART_H = 220;
  const ML = 44; // margin left
  const MR = 12; // margin right
  const MT = 16; // margin top
  const MB = 28; // margin bottom
  const PLOT_W = CHART_W - ML - MR; // 264
  const PLOT_H = CHART_H - MT - MB;

  // Ensure exactly 7 entries; filled left with zeros for missing days
  const DEFAULT_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const entries = $derived<PollHistoryEntry[]>(
    history.length >= 7
      ? history.slice(0, 7)
      : [
          ...DEFAULT_DAYS.slice(0, 7 - history.length).map((day) => ({ day, duration_s: 0 })),
          ...history,
        ]
  );

  const maxDur = $derived(Math.max(...entries.map((e) => e.duration_s), 0.01));
  // Round y-axis max up to nearest 5 (minimum 5)
  const yMax = $derived(Math.max(5, Math.ceil(maxDur / 5) * 5));

  // Compute SVG coordinates for each data point
  const points = $derived(
    entries.map((e, i) => ({
      x: ML + (i / 6) * PLOT_W,
      y: MT + PLOT_H - (e.duration_s / yMax) * PLOT_H,
      day: e.day,
      dur: e.duration_s,
    }))
  );

  const polylinePoints = $derived(points.map((p) => `${p.x},${p.y}`).join(' '));

  // Area fill: polygon closing back along the baseline
  const areaPoints = $derived(
    [
      `${ML},${MT + PLOT_H}`,
      ...points.map((p) => `${p.x},${p.y}`),
      `${ML + PLOT_W},${MT + PLOT_H}`,
    ].join(' ')
  );

  // Y-axis mid-point label (halfway between 0 and yMax)
  const yMid = $derived(Math.round(yMax / 2));
</script>

<div class="chart-container" data-testid="poll-runtime-chart">
  <h3 class="chart-title">Poll Runtimes (Last 7 Days)</h3>
  <svg
    viewBox="0 0 {CHART_W} {CHART_H}"
    preserveAspectRatio="xMidYMid meet"
    role="img"
    aria-label="Poll runtimes last 7 days"
    class="chart-svg"
  >
    <!-- Area fill under curve -->
    <polygon points={areaPoints} fill="var(--color-accent-teal-dim)" stroke="none" />

    <!-- Line chart -->
    <polyline
      points={polylinePoints}
      fill="none"
      stroke="var(--color-accent-teal)"
      stroke-width="2"
      stroke-linejoin="round"
      stroke-linecap="round"
    />

    <!-- Dot markers -->
    {#each points as pt}
      <circle cx={pt.x} cy={pt.y} r="3.5" fill="var(--color-accent-teal)" stroke="var(--surface-card)" stroke-width="1.5">
        <title>{pt.day}: {pt.dur}s</title>
      </circle>
    {/each}

    <!-- X-axis baseline -->
    <line
      x1={ML}
      y1={MT + PLOT_H}
      x2={ML + PLOT_W}
      y2={MT + PLOT_H}
      stroke="var(--border-default)"
      stroke-width="1"
    />

    <!-- Y-axis -->
    <line
      x1={ML}
      y1={MT}
      x2={ML}
      y2={MT + PLOT_H}
      stroke="var(--border-default)"
      stroke-width="1"
    />

    <!-- X-axis day labels -->
    {#each points as pt}
      <text x={pt.x} y={MT + PLOT_H + 16} text-anchor="middle" class="axis-label">{pt.day}</text>
    {/each}

    <!-- Y-axis labels: 0, mid, max -->
    <text x={ML - 6} y={MT + PLOT_H + 4} text-anchor="end" class="axis-label">0s</text>
    <text x={ML - 6} y={MT + PLOT_H / 2 + 4} text-anchor="end" class="axis-label">{yMid}s</text>
    <text x={ML - 6} y={MT + 4} text-anchor="end" class="axis-label">{yMax}s</text>
  </svg>
</div>

<style>
  .chart-container {
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
    display: grid;
    grid-template-rows: auto 1fr;
    min-height: 0;
  }

  .chart-title {
    margin: 0 0 var(--space-3);
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .chart-svg {
    width: 100%;
    height: 100%;
    display: block;
  }

  .axis-label {
    font-size: var(--text-sm);
    font-weight: var(--text-sm-weight);
    fill: var(--text-muted);
    font-family: var(--font-family-base, sans-serif);
  }
</style>
