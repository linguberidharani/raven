import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { forgotPassword } from '../api/auth';
import { ApiError } from '../api/errors';
import AuthLayout from '../components/AuthLayout';
import { TextField } from '../components/FormField';
import { Icon } from '../components/Icons';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { validateForgotPassword } from '../utils/validation';

/** Requests a password reset email. The answer is the same whether or not the address has an account, so the
 * success message never says which; it just repeats back what the person typed. */
export default function ForgotPassword() {
  useDocumentTitle('Reset your password');
  const [email, setEmail] = useState('');
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState(null);
  const form = useRef(null);

  useEffect(() => {
    form.current?.querySelector('[aria-invalid="true"]')?.focus();
  }, [errors]);

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    const found = validateForgotPassword({ email });
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      await forgotPassword({ email });
      setSentTo(email.trim());
    } catch (error) {
      setFormError(error instanceof ApiError ? error.detail : 'The request failed. Try again.');
    } finally {
      setBusy(false);
    }
  };

  if (sentTo) {
    return (
      <AuthLayout>
        <div>
          <h1>Check your email</h1>
          <p className="page-subtitle">
            If an account exists for <strong>{sentTo}</strong>, a password reset email has been sent. It may take a few minutes to arrive.
          </p>
        </div>
        <p className="auth-footer">
          <Link to="/login">Back to sign in</Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div>
        <h1>Reset your password</h1>
        <p className="page-subtitle">Enter your email and we&rsquo;ll send you a link to choose a new one.</p>
      </div>
      {formError ? (
        <div className="banner banner-error" role="alert">
          <Icon name="alert" />
          <div className="banner-body">{formError}</div>
        </div>
      ) : null}
      <form className="auth-form" onSubmit={submit} noValidate ref={form}>
        <TextField label="Email" type="email" value={email} onChange={setEmail} error={errors.email} autoComplete="email" inputMode="email" />
        <button type="submit" className="btn" disabled={busy}>
          {busy ? 'Sending\u2026' : 'Send reset link'}
        </button>
      </form>
      <p className="auth-footer">
        <Link to="/login">Back to sign in</Link>
      </p>
    </AuthLayout>
  );
}
