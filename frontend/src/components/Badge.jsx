import { basisInfo, severityInfo, statusInfo } from '../utils/mapping';

export function Badge({ tone = 'neutral', children, title }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

/** The severity of a rule, a group or an investigation as the API sends it. Always shows its name. */
export function SeverityBadge({ value }) {
  const info = severityInfo(value);
  return <Badge tone={info.key}>{info.label}</Badge>;
}

export function StatusBadge({ value }) {
  const info = statusInfo(value);
  return <Badge tone={info.tone}>{info.label}</Badge>;
}

/** Observed (recorded in the telemetry, solid teal) or derived (calculated or interpreted, dashed violet). */
export function BasisBadge({ basis }) {
  const info = basisInfo(basis);
  if (info === null) return null;
  return <Badge tone={info.key}>{info.label}</Badge>;
}
