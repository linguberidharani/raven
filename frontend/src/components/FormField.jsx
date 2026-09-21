import { useId, useState } from 'react';
import { Icon } from './Icons';

function ids(base, hint, error) {
  const describedBy = [hint ? `${base}-hint` : null, error ? `${base}-error` : null].filter(Boolean).join(' ');
  return describedBy || undefined;
}

/** A labelled text input. The error and the hint are linked to the input for screen readers. */
export function TextField({ label, value, onChange, error, hint, optional = false, type = 'text', ...rest }) {
  const base = useId();
  return (
    <div className="field">
      <label className="field-label" htmlFor={base}>
        {label}
        {optional ? <span className="field-optional"> (optional)</span> : null}
      </label>
      <input
        id={base}
        className="input"
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={ids(base, hint, error)}
        {...rest}
      />
      {hint ? (
        <div id={`${base}-hint`} className="field-hint">
          {hint}
        </div>
      ) : null}
      {error ? (
        <div id={`${base}-error`} className="field-error">
          {error}
        </div>
      ) : null}
    </div>
  );
}

/** A password input with a show/hide button. */
export function PasswordField({ label, value, onChange, error, hint, ...rest }) {
  const base = useId();
  const [visible, setVisible] = useState(false);
  return (
    <div className="field">
      <label className="field-label" htmlFor={base}>
        {label}
      </label>
      <div className="input-group">
        <input
          id={base}
          className="input"
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={ids(base, hint, error)}
          {...rest}
        />
        <button type="button" className="icon-btn" onClick={() => setVisible((shown) => !shown)} aria-pressed={visible} aria-label={visible ? 'Hide password' : 'Show password'}>
          <Icon name={visible ? 'eye-off' : 'eye'} />
        </button>
      </div>
      {hint ? (
        <div id={`${base}-hint`} className="field-hint">
          {hint}
        </div>
      ) : null}
      {error ? (
        <div id={`${base}-error`} className="field-error">
          {error}
        </div>
      ) : null}
    </div>
  );
}

/** A labelled multi-line input, linked to its hint and error like TextField. */
export function TextArea({ label, value, onChange, error, hint, optional = false, rows = 4, ...rest }) {
  const base = useId();
  return (
    <div className="field">
      <label className="field-label" htmlFor={base}>
        {label}
        {optional ? <span className="field-optional"> (optional)</span> : null}
      </label>
      <textarea
        id={base}
        className="input textarea"
        rows={rows}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={ids(base, hint, error)}
        {...rest}
      />
      {hint ? (
        <div id={`${base}-hint`} className="field-hint">
          {hint}
        </div>
      ) : null}
      {error ? (
        <div id={`${base}-error`} className="field-error">
          {error}
        </div>
      ) : null}
    </div>
  );
}
