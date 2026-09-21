import { useEffect, useRef, useState } from 'react';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/errors';
import AuthLayout from '../components/AuthLayout';
import { PasswordField, TextField } from '../components/FormField';
import { Icon } from '../components/Icons';
import { useAuth } from '../auth/AuthContext';
import { PASSWORD_MAX, PASSWORD_MIN, validateRegister } from '../utils/validation';

const FIELDS = ['name', 'email', 'organization', 'password'];

export default function Register() {
  useDocumentTitle('Create an account');
  const { register } = useAuth();
  const [values, setValues] = useState({ name: '', email: '', organization: '', password: '', confirm: '' });
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
    const found = validateRegister(values);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      await register(values);
    } catch (error) {
      setBusy(false);
      if (error instanceof ApiError && error.code === 'email_already_registered') {
        setErrors({ email: 'An account with this email address already exists. Sign in instead.' });
      } else if (error instanceof ApiError && error.code === 'validation_error' && FIELDS.some((name) => error.fields[name])) {
        setErrors(Object.fromEntries(FIELDS.filter((name) => error.fields[name]).map((name) => [name, error.fields[name]])));
      } else {
        setFormError(error instanceof ApiError ? error.detail : 'Registration failed. Try again.');
      }
    }
  };

  return (
    <AuthLayout>
      <div>
        <h1>Create an analyst account</h1>
        <p className="page-subtitle">Accounts are stored on this RAVEN installation only.</p>
      </div>
      {formError ? (
        <div className="banner banner-error" role="alert">
          <Icon name="alert" />
          <div className="banner-body">{formError}</div>
        </div>
      ) : null}
      <form className="auth-form" onSubmit={submit} noValidate ref={form}>
        <TextField label="Name" value={values.name} onChange={set('name')} error={errors.name} autoComplete="name" />
        <TextField label="Email" type="email" value={values.email} onChange={set('email')} error={errors.email} autoComplete="email" inputMode="email" />
        <TextField label="Organization" optional value={values.organization} onChange={set('organization')} error={errors.organization} autoComplete="organization" />
        <PasswordField
          label="Password"
          value={values.password}
          onChange={set('password')}
          error={errors.password}
          hint={`${PASSWORD_MIN} to ${PASSWORD_MAX} characters.`}
          autoComplete="new-password"
        />
        <PasswordField label="Confirm password" value={values.confirm} onChange={set('confirm')} error={errors.confirm} autoComplete="new-password" />
        <button type="submit" className="btn" disabled={busy}>
          {busy ? 'Creating account\u2026' : 'Create account'}
        </button>
      </form>
      <p className="auth-footer">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </AuthLayout>
  );
}
