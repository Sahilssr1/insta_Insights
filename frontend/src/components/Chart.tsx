import { useMemo, useState } from 'react';

const COLORS = ['#6c8cff', '#34d399', '#fbbf24', '#f472b6', '#22d3ee', '#a78bfa'];

export interface Series {
  name: string;
  color?: string;
  points: { x: string; y: number | null }[];
}

/** Responsive SVG time-series chart with hover tooltip. No external deps. */
export function TimeChart({ series, height = 260 }: { series: Series[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 720;
  const H = height;
  const PAD = { l: 46, r: 12, t: 14, b: 30 };

  const { paths, yTicks, xLabels, allX } = useMemo(() => {
    const allX: string[] = [];
    series.forEach((s) => s.points.forEach((p) => { if (!allX.includes(p.x)) allX.push(p.x); }));
    allX.sort();
    let maxY = 0;
    series.forEach((s) => s.points.forEach((p) => { if (p.y !== null && p.y > maxY) maxY = p.y; }));
    if (maxY === 0) maxY = 1;
    maxY *= 1.12;

    const x = (i: number) => PAD.l + (i / Math.max(1, allX.length - 1)) * (W - PAD.l - PAD.r);
    const y = (v: number) => PAD.t + (1 - v / maxY) * (H - PAD.t - PAD.b);

    const paths = series.map((s, si) => {
      const color = s.color || COLORS[si % COLORS.length];
      let d = '';
      s.points.forEach((p) => {
        const i = allX.indexOf(p.x);
        if (p.y === null) return;
        d += `${d ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.y).toFixed(1)} `;
      });
      // area fill
      const first = s.points.find((p) => p.y !== null);
      const last = [...s.points].reverse().find((p) => p.y !== null);
      let area = '';
      if (first && last) {
        const i0 = allX.indexOf(first.x), i1 = allX.indexOf(last.x);
        area = `${d}L${x(i1).toFixed(1)},${y(0).toFixed(1)} L${x(i0).toFixed(1)},${y(0).toFixed(1)} Z`;
      }
      return { d: d.trim(), area, color, name: s.name };
    });

    const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => ({ v: maxY / 1.12 * f, y: y(maxY / 1.12 * f) }));
    const step = Math.max(1, Math.floor(allX.length / 6));
    const xLabels = allX.filter((_, i) => i % step === 0 || i === allX.length - 1)
      .map((lx) => ({ x: lx, pos: x(allX.indexOf(lx)) }));
    return { paths, yTicks, xLabels, allX };
  }, [series, H]);

  const fmtTick = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k` : `${Math.round(v)}`);
  const fmtX = (iso: string) => {
    const d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const frac = (px - PAD.l) / (W - PAD.l - PAD.r);
    const idx = Math.round(frac * (allX.length - 1));
    setHover(Math.max(0, Math.min(allX.length - 1, idx)));
  };

  const hoverX = hover !== null ? PAD.l + (hover / Math.max(1, allX.length - 1)) * (W - PAD.l - PAD.r) : 0;

  return (
    <div>
      <div className="chart-legend">
        {paths.map((p) => (
          <span key={p.name} className="item"><span className="dot" style={{ background: p.color }} />{p.name}</span>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}
      >
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.l} x2={W - PAD.r} y1={t.y} y2={t.y} stroke="#1c2433" strokeWidth={1} />
            <text x={PAD.l - 8} y={t.y + 4} textAnchor="end" fontSize={10.5} fill="#5f6b82">{fmtTick(t.v)}</text>
          </g>
        ))}
        {xLabels.map((l) => (
          <text key={l.x} x={l.pos} y={H - 10} textAnchor="middle" fontSize={10.5} fill="#5f6b82">{fmtX(l.x)}</text>
        ))}
        {paths.map((p, i) => (
          <g key={i}>
            {p.area && <path d={p.area} fill={p.color} opacity={0.10} />}
            <path d={p.d} fill="none" stroke={p.color} strokeWidth={2.2} strokeLinejoin="round" strokeLinecap="round" />
          </g>
        ))}
        {hover !== null && (
          <g>
            <line x1={hoverX} x2={hoverX} y1={PAD.t} y2={H - PAD.b} stroke="#3a4763" strokeWidth={1} strokeDasharray="4 3" />
            {series.map((s, si) => {
              const p = s.points.find((pt) => pt.x === allX[hover]);
              if (!p || p.y === null) return null;
              const maxY2 = Math.max(1, ...series.flatMap((ss) => ss.points.map((pp) => pp.y || 0))) * 1.12;
              const cy = PAD.t + (1 - p.y / maxY2) * (H - PAD.t - PAD.b);
              return <circle key={si} cx={hoverX} cy={cy} r={4} fill={s.color || COLORS[si % COLORS.length]} stroke="#0b0e14" strokeWidth={2} />;
            })}
          </g>
        )}
      </svg>
      {hover !== null && (
        <div style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: 6 }}>
          <strong style={{ color: 'var(--text)' }}>{fmtX(allX[hover])}</strong>
          {' — '}
          {series.map((s, si) => {
            const p = s.points.find((pt) => pt.x === allX[hover]);
            return p && p.y !== null ? (
              <span key={si} style={{ marginRight: 12 }}>
                <span style={{ color: s.color || COLORS[si % COLORS.length] }}>●</span> {s.name}: <strong style={{ color: 'var(--text)' }}>{Math.round(p.y).toLocaleString()}</strong>
              </span>
            ) : null;
          })}
        </div>
      )}
    </div>
  );
}
