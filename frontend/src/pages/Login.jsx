import { useEffect, useRef, useState } from 'react';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/errors';
import AuthLayout from '../components/AuthLayout';
import { PasswordField, TextField } from '../components/FormField';
import { Icon } from '../components/Icons';
import { useAuth } from '../auth/AuthContext';
import { validateLogin } from '../utils/validation';

export function messageForLoginError(error) {
  if (error instanceof ApiError) {
    if (error.code === 'invalid_credentials') return 'The email or the password is not correct.';
    return error.detail;
  }
  return 'Sign in failed. Try again.';
}

export default function Login() {
  useDocumentTitle('Sign in');
  const { login } = useAuth();
  const [values, setValues] = useState({ email: '', password: '' });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [busy, setBusy] = useState(false);
  const form = useRef(null);

  useEffect(() => {
    form.current?.querySelector('[aria-invalid="true"]')?.focus();
  }, [errors]);

  const set = (name) => (value) => setValues((previous) => ({ ...previous, [name]: value }));

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    const found = validateLogin(values);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      await login(values);
    } catch (error) {
      setBusy(false);
      if (error instanceof ApiError && error.code === 'validation_error' && Object.keys(error.fields).length > 0) {
        setErrors({ email: error.fields.email, password: error.fields.password });
      } else {
        setFormError(messageForLoginError(error));
      }
    }
  };

  return (
    <AuthLayout>
      <div>
        <h1>Analyst sign in</h1>
        <p className="page-subtitle">Access your investigation workspace.</p>
      </div>
      {formError ? (
        <div className="banner banner-error" role="alert">
          <Icon name="alert" />
          <div className="banner-body">{formError}</div>
        </div>
      ) : null}
      <form className="auth-form" onSubmit={submit} noValidate ref={form}>
        <TextField label="Email" type="email" value={values.email} onChange={set('email')} error={errors.email} autoComplete="email" inputMode="email" />
        <PasswordField label="Password" value={values.password} onChange={set('password')} error={errors.password} autoComplete="current-password" />
        <button type="submit" className="btn" disabled={busy}>
          {busy ? 'Signing in\u2026' : 'Sign in'}
        </button>
      </form>
      <p className="auth-footer">
        No account yet? <Link to="/register">Create an account</Link>
      </p>
    </AuthLayout>
  );
}
