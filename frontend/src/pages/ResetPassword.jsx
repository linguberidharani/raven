import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { resetPassword } from '../api/auth';
import { ApiError } from '../api/errors';
import AuthLayout from '../components/AuthLayout';
import { PasswordField } from '../components/FormField';
import { Icon } from '../components/Icons';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { PASSWORD_MAX, PASSWORD_MIN, validateResetPassword } from '../utils/validation';

/** Sets a new password from the token in a reset email link (?token=...). Resetting signs the account out
 * everywhere, so success leads back to sign in rather than in directly. */
export default function ResetPassword() {
  useDocumentTitle('Choose a new password');
  const [searchParams] = useSearchParams();
  const token = (searchParams.get('token') ?? '').trim();
  const [values, setValues] = useState({ password: '', confirm: '' });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [tokenError, setTokenError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const form = useRef(null);

  useEffect(() => {
    form.current?.querySelector('[aria-invalid="true"]')?.focus();
  }, [errors]);

  const set = (name) => (value) => setValues((previous) => ({ ...previous, [name]: value }));

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    const found = validateResetPassword(values);
    setErrors(found);
    setFormError(null);
    setTokenError(null);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      await resetPassword({ token, password: values.password });
      setDone(true);
    } catch (error) {
      if (error instanceof ApiError && error.code === 'invalid_reset_token') {
        setTokenError(error.detail);
      } else if (error instanceof ApiError && error.code === 'validation_error' && error.fields.password) {
        setErrors({ password: error.fields.password });
      } else {
        setFormError(error instanceof ApiError ? error.detail : 'The request failed. Try again.');
      }
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <AuthLayout>
        <div>
          <h1>This link is not complete</h1>
          <p className="page-subtitle">The web address is missing its reset token. Request a new password reset link.</p>
        </div>
        <p className="auth-footer">
          <Link to="/forgot-password">Request a new link</Link>
        </p>
      </AuthLayout>
    );
  }

  if (done) {
    return (
      <AuthLayout>
        <div>
          <h1>Password updated</h1>
          <p className="page-subtitle">Your password has been changed. Sign in with your new password &mdash; you were signed out everywhere else too.</p>
        </div>
        <Link className="btn" to="/login">
          Go to sign in
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div>
        <h1>Choose a new password</h1>
        <p className="page-subtitle">This link works once. Choosing a password below uses it.</p>
      </div>
      {tokenError ? (
        <div className="banner banner-error" role="alert">
          <Icon name="alert" />
          <div className="banner-body">
            {tokenError} <Link to="/forgot-password">Request a new link</Link>.
          </div>
        </div>
      ) : null}
      {formError ? (
        <div className="banner banner-error" role="alert">
          <Icon name="alert" />
          <div className="banner-body">{formError}</div>
        </div>
      ) : null}
      <form className="auth-form" onSubmit={submit} noValidate ref={form}>
        <PasswordField
          label="New password"
          value={values.password}
          onChange={set('password')}
          error={errors.password}
          hint={`${PASSWORD_MIN} to ${PASSWORD_MAX} characters.`}
          autoComplete="new-password"
        />
        <PasswordField label="Confirm new password" value={values.confirm} onChange={set('confirm')} error={errors.confirm} autoComplete="new-password" />
        <button type="submit" className="btn" disabled={busy}>
          {busy ? 'Updating\u2026' : 'Update password'}
        </button>
      </form>
      <p className="auth-footer">
        <Link to="/login">Back to sign in</Link>
      </p>
    </AuthLayout>
  );
}
