import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import AppShell from './components/AppShell';
import { DemoBanner } from './components/DemoBanner';
import { PublicOnly, RequireAuth } from './components/RouteGuards';
import Dashboard from './pages/Dashboard';
import InvestigationLayout from './pages/InvestigationLayout';
import InvestigationStep from './pages/InvestigationStep';
import Investigations from './pages/Investigations';
import Intro from './pages/Intro';
import Login from './pages/Login';
import NotFound from './pages/NotFound';
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
          <Route path="/investigations" element={<Investigations />} />
          <Route path="/investigations/:id" element={<InvestigationLayout />}>
            <Route index element={<Navigate to="evidence" replace />} />
            <Route path=":step" element={<InvestigationStep />} />
          </Route>
          <Route path="/profile" element={<Profile />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
