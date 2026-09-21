import { getReconstruction } from '../api/investigations';
import { useApi } from '../hooks/useApi';
import { formatTimestamp } from '../utils/format';

/** A choice between attack sessions. It shows nothing when there is at most one. */
export function SessionPicker({ investigationId, value, onChange }) {
  const { data } = useApi((signal) => getReconstruction(investigationId, signal), [investigationId]);
  const sessions = data?.sessions ?? [];
  if (sessions.length < 2) return null;
  return (
    <div className="toolbar">
      <label htmlFor="session-picker" className="field-label">Attack session</label>
      <select id="session-picker" className="input select" value={value ?? sessions[0].session_id} onChange={(event) => onChange(event.target.value)}>
        {sessions.map((session) => (
          <option key={session.session_id} value={session.session_id}>
            {formatTimestamp(session.start_time)} · {session.computer} · {session.group_count} groups
          </option>
        ))}
      </select>
    </div>
  );
}
