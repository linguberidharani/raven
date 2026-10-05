// Form checks that run before a request. The server checks everything again; these only save a round trip
// and give clear messages. The limits are those of docs/api-contract.md.

export const PASSWORD_MIN = 10;
export const PASSWORD_MAX = 128;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(value) {
  return typeof value === 'string' && value.length <= 254 && EMAIL.test(value.trim());
}

export function validateLogin({ email, password }) {
  const errors = {};
  if (!email || !email.trim()) errors.email = 'Enter your email address.';
  else if (!isValidEmail(email)) errors.email = 'Enter a valid email address.';
  if (!password) errors.password = 'Enter your password.';
  return errors;
}

export function validateRegister({ name, email, organization, password, confirm }) {
  const errors = {};
  const cleanName = (name ?? '').trim();
  if (!cleanName) errors.name = 'Enter your name.';
  else if (cleanName.length > 100) errors.name = 'Use at most 100 characters.';
  if (!email || !email.trim()) errors.email = 'Enter your email address.';
  else if (!isValidEmail(email)) errors.email = 'Enter a valid email address.';
  if ((organization ?? '').trim().length > 100) errors.organization = 'Use at most 100 characters.';
  if (!password) errors.password = 'Choose a password.';
  else if (password.length < PASSWORD_MIN) errors.password = `Use at least ${PASSWORD_MIN} characters.`;
  else if (password.length > PASSWORD_MAX) errors.password = `Use at most ${PASSWORD_MAX} characters.`;
  else if (!password.trim()) errors.password = 'The password cannot be only spaces.';
  if (!errors.password && password !== confirm) errors.confirm = 'The two passwords are not the same.';
  return errors;
}

export function validateForgotPassword({ email }) {
  const errors = {};
  if (!email || !email.trim()) errors.email = 'Enter your email address.';
  else if (!isValidEmail(email)) errors.email = 'Enter a valid email address.';
  return errors;
}

export function validateResetPassword({ password, confirm }) {
  const errors = {};
  if (!password) errors.password = 'Choose a new password.';
  else if (password.length < PASSWORD_MIN) errors.password = `Use at least ${PASSWORD_MIN} characters.`;
  else if (password.length > PASSWORD_MAX) errors.password = `Use at most ${PASSWORD_MAX} characters.`;
  else if (!password.trim()) errors.password = 'The password cannot be only spaces.';
  if (!errors.password && password !== confirm) errors.confirm = 'The two passwords are not the same.';
  return errors;
}

function hasControlCharacter(text) {
  for (let index = 0; index < text.length; index += 1) {
    if (text.charCodeAt(index) < 32) return true;
  }
  return false;
}

/** Only a path inside this app may be used to go back after sign-in (no other site, no protocol tricks). */
export function safeNextPath(next, fallback = '/dashboard') {
  if (typeof next !== 'string') return fallback;
  if (!next.startsWith('/') || next.startsWith('//') || next.includes('\\') || hasControlCharacter(next)) return fallback;
  if (next === '/' || next.startsWith('/login') || next.startsWith('/register')) return fallback;
  return next;
}
