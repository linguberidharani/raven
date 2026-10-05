import { describe, expect, it } from 'vitest';
import { isValidEmail, safeNextPath, validateLogin, validateRegister } from './validation';

describe('isValidEmail', () => {
  it('accepts normal addresses and rejects the rest', () => {
    expect(isValidEmail('ada@example.com')).toBe(true);
    expect(isValidEmail(' ada@example.com ')).toBe(true);
    for (const value of ['', 'ada', 'ada@', '@example.com', 'ada@example', 'a b@example.com', null, 5]) expect(isValidEmail(value)).toBe(false);
    expect(isValidEmail('a'.repeat(250) + '@x.com')).toBe(false);
  });
});

describe('validateLogin', () => {
  it('needs an email and a password', () => {
    expect(validateLogin({ email: '', password: '' })).toEqual({ email: 'Enter your email address.', password: 'Enter your password.' });
    expect(validateLogin({ email: 'nope', password: 'x' })).toEqual({ email: 'Enter a valid email address.' });
    expect(validateLogin({ email: 'ada@example.com', password: 'x' })).toEqual({});
  });
});

describe('validateRegister', () => {
  const good = { name: 'Ada', email: 'ada@example.com', organization: '', password: 'correct horse', confirm: 'correct horse' };
  it('accepts good values', () => {
    expect(validateRegister(good)).toEqual({});
    expect(validateRegister({ ...good, organization: 'Analytical Engines' })).toEqual({});
  });
  it('checks each field', () => {
    expect(validateRegister({ ...good, name: '  ' }).name).toBe('Enter your name.');
    expect(validateRegister({ ...good, name: 'x'.repeat(101) }).name).toBe('Use at most 100 characters.');
    expect(validateRegister({ ...good, email: 'bad' }).email).toBe('Enter a valid email address.');
    expect(validateRegister({ ...good, organization: 'x'.repeat(101) }).organization).toBe('Use at most 100 characters.');
  });
  it('checks the password rules of the API', () => {
    expect(validateRegister({ ...good, password: '', confirm: '' }).password).toBe('Choose a password.');
    expect(validateRegister({ ...good, password: 'short', confirm: 'short' }).password).toBe('Use at least 10 characters.');
    expect(validateRegister({ ...good, password: 'x'.repeat(129), confirm: 'x'.repeat(129) }).password).toBe('Use at most 128 characters.');
    expect(validateRegister({ ...good, password: ' '.repeat(12), confirm: ' '.repeat(12) }).password).toBe('The password cannot be only spaces.');
    expect(validateRegister({ ...good, password: 'x'.repeat(10), confirm: 'x'.repeat(10) })).toEqual({});
    expect(validateRegister({ ...good, password: 'x'.repeat(128), confirm: 'x'.repeat(128) })).toEqual({});
  });
  it('checks the confirmation only when the password itself is fine', () => {
    expect(validateRegister({ ...good, confirm: 'other password' })).toEqual({ confirm: 'The two passwords are not the same.' });
    expect(validateRegister({ ...good, password: 'short', confirm: 'other' }).confirm).toBeUndefined();
  });
});

describe('safeNextPath', () => {
  it('keeps paths inside the app', () => {
    expect(safeNextPath('/investigations/3/timeline')).toBe('/investigations/3/timeline');
    expect(safeNextPath('/profile?tab=1')).toBe('/profile?tab=1');
  });
  it('refuses everything else', () => {
    for (const value of ['https://evil.example', '//evil.example', '/\\evil', 'javascript:alert(1)', '', null, undefined, 5, '/a\nb', '/login', '/register', '/']) {
      expect(safeNextPath(value)).toBe('/dashboard');
    }
    expect(safeNextPath('https://evil.example', '/investigations')).toBe('/investigations');
  });
});
