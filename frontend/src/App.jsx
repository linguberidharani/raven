import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import AppShell from './components/AppShell';
import { DemoBanner } from './components/DemoBanner';
import { PublicOnly, RequireAuth } from './components/RouteGuards';
import Dashboard from './pages/Dashboard';
import InvestigationStep from './pages/InvestigationStep';
import Intro from './pages/Intro';
import Login from './pages/Login';
import NotFound from './pages/NotFound';
import Planned from './pages/Planned';
import Profile from './pages/Profile';
import Register from './pages/Register';
import Settings from './pages/Settings';

export default function App() {
  return (
    <AuthProvider>
      <DemoBanner />
      <Routes>
        <Route path="/" element={<Intro />} />
        <Route
          path="/login"
          element={
            <PublicOnly>
              <Login />
            </PublicOnly>
          }
        />
        <Route
          path="/register"
          element={
            <PublicOnly>
              <Register />
            </PublicOnly>
          }
        />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/investigations" element={<Planned title="Investigations" subtitle="All investigations, with search and filters." endpoints={['GET /api/investigations', 'POST /api/investigations']} />} />
          <Route path="/investigations/:id" element={<Navigate to="evidence" replace />} />
          <Route path="/investigations/:id/:step" element={<InvestigationStep />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
