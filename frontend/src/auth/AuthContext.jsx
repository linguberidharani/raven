import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { ApiError } from '../api/errors';
import { getMe, login as apiLogin, logout as apiLogout, register as apiRegister } from '../api/auth';
import { setUnauthorizedHandler } from '../api/client';

const AuthContext = createContext(null);

const ANONYMOUS = { status: 'anonymous', user: null, error: null };
// After an explicit sign out nobody wants to be sent back to the page they left.
const SIGNED_OUT = { status: 'anonymous', user: null, error: null, signedOut: true };

/**
 * status: 'loading' (asking the server), 'authenticated', 'anonymous' or 'error' (the server could not be asked).
 * The session itself lives in an HttpOnly cookie; the browser code never sees a token.
 */
export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: 'loading', user: null, error: null });

  const reload = useCallback(async () => {
    setState({ status: 'loading', user: null, error: null });
    try {
      const user = await getMe();
      setState({ status: 'authenticated', user, error: null });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) setState(ANONYMOUS);
      else setState({ status: 'error', user: null, error });
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    setUnauthorizedHandler(() => setState(ANONYMOUS));
    return () => setUnauthorizedHandler(null);
  }, []);

  const login = useCallback(async (credentials) => {
    const user = await apiLogin(credentials);
    setState({ status: 'authenticated', user, error: null });
    return user;
  }, []);

  const register = useCallback(
    async (values) => {
      await apiRegister(values);
      return login({ email: values.email, password: values.password });
    },
    [login],
  );

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) throw error;
    }
    setState(SIGNED_OUT);
  }, []);

  const value = useMemo(() => ({ ...state, reload, login, register, logout }), [state, reload, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (value === null) throw new Error('useAuth must be used inside an AuthProvider');
  return value;
}
