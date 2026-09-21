import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { formatClock } from '../utils/format';

const SERIES = [
  { key: 'process_creation', label: 'Process created', color: '#5a9df5' },
  { key: 'network_connection', label: 'Network connection', color: '#3db7aa' },
  { key: 'file_create', label: 'File created', color: '#e8bb4a' },
];

const AXIS = { stroke: '#7d8aa1', fontSize: 12 };

/** Events per time bucket, stacked by event type. The same numbers are in a table for screen readers. */
export default function ActivityChart({ buckets, bucketSeconds }) {
  const data = buckets.map((bucket) => ({ ...bucket, time: formatClock(bucket.start).slice(0, 8) }));
  return (
    <div role="img" aria-label={`Events over time in buckets of ${bucketSeconds} seconds, by event type. The data is also available as a table.`}>
      <ResponsiveContainer width="100%" height={300} initialDimension={{ width: 800, height: 300 }}>
        <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="#1b2637" vertical={false} />
          <XAxis dataKey="time" tick={AXIS} axisLine={{ stroke: '#263349' }} tickLine={false} minTickGap={28} />
          <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} width={44} />
          <Tooltip
            cursor={{ fill: 'rgba(90,157,245,0.08)' }}
            contentStyle={{ background: '#17202e', border: '1px solid #263349', borderRadius: 6, color: '#e8edf6' }}
            labelFormatter={(label) => `${label} UTC`}
          />
          <Legend wrapperStyle={{ color: '#a5b1c6', fontSize: 13 }} />
          {SERIES.map((series) => (
            <Bar key={series.key} dataKey={series.key} name={series.label} stackId="events" fill={series.color} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
