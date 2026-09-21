import { useState } from 'react';
import { Icon } from './Icons';

export const ARRAY_LIMIT = 50;

function Primitive({ value }) {
  if (value === null) return <span className="json-null">null</span>;
  if (typeof value === 'string') return <span className="json-string">&quot;{value}&quot;</span>;
  if (typeof value === 'number') return <span className="json-number">{value}</span>;
  return <span className="json-boolean">{String(value)}</span>;
}

function Node({ name, value, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const [all, setAll] = useState(false);

  if (value === null || typeof value !== 'object') {
    return (
      <div className="json-row">
        <span className="json-key">{name}</span>
        <span className="faint">: </span>
        <Primitive value={value} />
      </div>
    );
  }

  const isArray = Array.isArray(value);
  const entries = isArray ? value.map((item, index) => [index, item]) : Object.entries(value);
  const shown = all ? entries : entries.slice(0, ARRAY_LIMIT);
  return (
    <div className="json-node">
      <button type="button" className="json-toggle" aria-expanded={open} onClick={() => setOpen((previous) => !previous)}>
        <Icon name="arrow" size={14} />
        <span className="json-key">{name}</span>
        <span className="faint mono">{isArray ? `[${entries.length}]` : `{${entries.length}}`}</span>
      </button>
      {open ? (
        <div className="json-children">
          {shown.map(([key, child]) => (
            <Node key={key} name={key} value={child} />
          ))}
          {entries.length > shown.length ? (
            <button type="button" className="btn btn-ghost small" onClick={() => setAll(true)}>
              Show all {entries.length} items
            </button>
          ) : null}
          {entries.length === 0 ? <span className="faint">empty</span> : null}
        </div>
      ) : null}
    </div>
  );
}

/** A document as a tree that opens branch by branch. Only the open branches are drawn. */
export function JsonTree({ data, openKeys = [] }) {
  return (
    <div className="json-tree" role="group" aria-label="Structured document">
      {Object.entries(data).map(([key, value]) => (
        <Node key={key} name={key} value={value} defaultOpen={openKeys.includes(key)} />
      ))}
    </div>
  );
}
