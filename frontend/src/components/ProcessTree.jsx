import { useMemo, useState } from 'react';
import { formatClock, formatNumber } from '../utils/format';
import { eventTypeLabel, pathBasename } from '../utils/mapping';
import { Badge } from './Badge';
import { Icon } from './Icons';

function Node({ node, byGuid, expanded, toggle, path }) {
  const children = node.child_guids.map((guid) => byGuid.get(guid)).filter((child) => child && !path.has(child.process_guid));
  const open = expanded.has(node.process_guid);
  const name = pathBasename(node.image) || 'unknown process';
  const counts = Object.entries(node.event_counts ?? {});
  const next = new Set(path).add(node.process_guid);
  return (
    <li className={`tree-node${node.in_session ? '' : ' outside'}`}>
      <div className="tree-row">
        {children.length > 0 ? (
          <button type="button" className="tree-toggle" onClick={() => toggle(node.process_guid)} aria-expanded={open} aria-label={`${open ? 'Collapse' : 'Expand'} ${name} (${node.process_id})`}>
            <Icon name="arrow" size={14} />
          </button>
        ) : (
          <span className="tree-toggle spacer" aria-hidden="true" />
        )}
        <div className="tree-card">
          <div className="tree-title">
            <span className="mono tree-name" title={node.image}>{name}</span>
            <span className="mono faint">PID {node.process_id}</span>
            {node.in_session ? <Badge tone="success">In session</Badge> : <Badge tone="neutral">Outside the session</Badge>}
          </div>
          <div className="tree-meta">
            {node.user ? <span>{node.user}</span> : null}
            {node.first_seen ? <span>first seen {formatClock(node.first_seen)} UTC</span> : <span>no events in the session</span>}
            {node.group_ids.length > 0 ? <span>{formatNumber(node.group_ids.length)} groups</span> : null}
            {counts.map(([type, count]) => (
              <span key={type} className="count-chip">
                {eventTypeLabel(type)} <strong>{formatNumber(count)}</strong>
              </span>
            ))}
          </div>
        </div>
      </div>
      {children.length > 0 && open ? (
        <ul className="tree-children">
          {children.map((child) => (
            <Node key={child.process_guid} node={child} byGuid={byGuid} expanded={expanded} toggle={toggle} path={next} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/** Parent and child processes of a session, from the process GUIDs recorded in the events. */
export function ProcessTree({ tree }) {
  const byGuid = useMemo(() => new Map(tree.nodes.map((node) => [node.process_guid, node])), [tree]);
  const withChildren = useMemo(() => tree.nodes.filter((node) => node.child_guids.length > 0).map((node) => node.process_guid), [tree]);
  const [expanded, setExpanded] = useState(() => new Set(tree.nodes.length <= 60 ? withChildren : tree.roots));

  const toggle = (guid) =>
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(guid)) next.delete(guid);
      else next.add(guid);
      return next;
    });

  const roots = tree.roots.map((guid) => byGuid.get(guid)).filter(Boolean);
  if (roots.length === 0) return <p className="faint">No process relations were recorded in this session.</p>;
  return (
    <div>
      <div className="actions">
        <button type="button" className="btn btn-secondary" onClick={() => setExpanded(new Set(withChildren))}>
          Expand all
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => setExpanded(new Set())}>
          Collapse all
        </button>
      </div>
      <ul className="tree" aria-label="Process tree">
        {roots.map((node) => (
          <Node key={node.process_guid} node={node} byGuid={byGuid} expanded={expanded} toggle={toggle} path={new Set()} />
        ))}
      </ul>
    </div>
  );
}
