import { formatNumber } from '../utils/format';

const RADIUS = 52;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const GAP = 2.5;

/** A ring chart. `segments` are { key, label, value, color }; the legend beside it carries the same numbers as text. */
export function Donut({ segments, centerLabel }) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  let offset = 0;
  const summary = segments.filter((segment) => segment.value > 0).map((segment) => `${segment.label} ${segment.value}`).join(', ');
  return (
    <svg className="donut" viewBox="0 0 140 140" role="img" aria-label={`${centerLabel}: ${total} in total. ${summary || 'None'}.`}>
      <circle cx="70" cy="70" r={RADIUS} fill="none" stroke="var(--surface-2)" strokeWidth="16" />
      {segments
        .filter((segment) => segment.value > 0)
        .map((segment) => {
          const length = (segment.value / total) * CIRCUMFERENCE;
          const visible = Math.max(length - (segments.filter((s) => s.value > 0).length > 1 ? GAP : 0), 0.5);
          const circle = (
            <circle
              key={segment.key}
              className="donut-segment"
              cx="70"
              cy="70"
              r={RADIUS}
              fill="none"
              stroke={segment.color}
              strokeWidth="16"
              strokeDasharray={`${visible} ${CIRCUMFERENCE - visible}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 70 70)"
            />
          );
          offset += length;
          return circle;
        })}
      <text x="70" y="68" textAnchor="middle" className="donut-total">
        {formatNumber(total)}
      </text>
      <text x="70" y="86" textAnchor="middle" className="donut-caption">
        {centerLabel}
      </text>
    </svg>
  );
}
