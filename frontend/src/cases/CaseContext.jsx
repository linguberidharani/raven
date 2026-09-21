import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { getInvestigation } from '../api/investigations';
import { useApi } from '../hooks/useApi';
import { matchInvestigation } from '../utils/navigation';

const KEY = 'raven.currentInvestigation';
const CaseContext = createContext(null);

function readStored() {
  try {
    const value = window.localStorage.getItem(KEY);
    return /^\d+$/.test(value ?? '') && Number(value) >= 1 ? Number(value) : null;
  } catch {
    return null;
  }
}

function writeStored(id) {
  try {
    if (id === null) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, String(id));
  } catch {
    // storage may be blocked: the workflow then only follows the address
  }
}

/**
 * The current investigation: the one in the address, otherwise the last one that was opened (kept in this browser
 * only). It is loaded once here for the sidebar, the top bar and the pages of the investigation.
 */
export function CaseProvider({ children }) {
  const { pathname } = useLocation();
  const routeId = matchInvestigation(pathname)?.id ?? null;
  const [storedId, setStoredId] = useState(readStored);
  const id = routeId ?? storedId;
  const { data, loading, error, reload } = useApi((signal) => (id === null ? Promise.resolve(null) : getInvestigation(id, signal)), [id]);
  const investigation = data && data.id === id ? data : null;

  useEffect(() => {
    if (investigation && routeId === investigation.id && storedId !== investigation.id) {
      setStoredId(investigation.id);
      writeStored(investigation.id);
    }
  }, [investigation, routeId, storedId]);

  useEffect(() => {
    if (error?.status === 404 && error.code === 'investigation_not_found' && id !== null && id === storedId) {
      setStoredId(null);
      writeStored(null);
    }
  }, [error, id, storedId]);

  const value = useMemo(
    () => ({ id, investigation, loading: id !== null && loading && investigation === null, error: id === null ? null : error, reload }),
    [id, investigation, loading, error, reload],
  );
  return <CaseContext.Provider value={value}>{children}</CaseContext.Provider>;
}

export function useCase() {
  const value = useContext(CaseContext);
  if (value === null) throw new Error('useCase must be used inside a CaseProvider');
  return value;
}
