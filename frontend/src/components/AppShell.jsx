import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { CaseProvider, useCase } from '../cases/CaseContext';
import { initials } from '../utils/mapping';
import { breadcrumbsFor } from '../utils/navigation';
import { Brand } from './Brand';
import { Breadcrumbs } from './Breadcrumbs';
import { Icon } from './Icons';
import { Sidebar } from './Sidebar';

function Frame() {
  const { user, logout } = useAuth();
  const { investigation } = useCase();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const main = useRef(null);
  const first = useRef(true);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    setOpen(false);
    if (first.current) {
      first.current = false;
      return;
    }
    main.current?.focus();
  }, [pathname]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const signOut = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar no-print">
        <button type="button" className="icon-btn menu-btn" onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open} aria-controls="sidebar">
          <Icon name="menu" />
        </button>
        <Link to="/dashboard" className="topbar-brand" aria-label="RAVEN dashboard">
          <Brand size={26} />
        </Link>
        <Breadcrumbs items={breadcrumbsFor(pathname, investigation?.code)} />
        <div className="topbar-spacer" />
        <Link to="/profile" className="user-chip" aria-label={`Profile of ${user?.name ?? 'the signed-in user'}`}>
          <span className="avatar" aria-hidden="true">
            {initials(user?.name)}
          </span>
          <span className="user-name">{user?.name}</span>
        </Link>
      </header>
      <Sidebar id="sidebar" open={open} onClose={close} onSignOut={signOut} />
      <main className="main" id="main" tabIndex={-1} ref={main}>
        <div className="route-fade" key={pathname.split('/').slice(0, 3).join('/')}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}

/** The frame of every signed-in page: skip link, top bar with breadcrumbs, sidebar (a drawer under 1024 px), main. */
export default function AppShell() {
  return (
    <CaseProvider>
      <Frame />
    </CaseProvider>
  );
}
