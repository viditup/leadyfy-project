import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './components/common/ToastProvider';
import ProtectedRoute from './components/common/ProtectedRoute';
import DashboardLayout from './components/layout/DashboardLayout';
import PortalLayout from './components/layout/PortalLayout';
import { ROLES } from './data/mockData';

import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Clients from './pages/Clients';
import ClientDetail from './pages/ClientDetail';
import Orders from './pages/Orders';
import Scripts from './pages/Scripts';
import Creators from './pages/Creators';
import Shoots from './pages/Shoots';
import Videos from './pages/Videos';
import Tasks from './pages/Tasks';
import Tickets from './pages/Tickets';
import Employees from './pages/Employees';
import Financials from './pages/Financials';
import Settings from './pages/Settings';
import NotFound from './pages/NotFound';

import PortalDashboard from './pages/portal/PortalDashboard';
import PortalScripts from './pages/portal/PortalScripts';
import PortalVideos from './pages/portal/PortalVideos';
import PortalBilling from './pages/portal/PortalBilling';

const STAFF_ROLES = [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE];

function RootRedirect() {
  const { user, ready } = useAuth();
  if (!ready) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === ROLES.CLIENT ? '/portal' : '/dashboard'} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<RootRedirect />} />

            {/* Internal (Owner / Admin / Employee) app */}
            <Route
              element={
                <ProtectedRoute allow={STAFF_ROLES}>
                  <DashboardLayout />
                </ProtectedRoute>
              }
            >
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/clients" element={<Clients />} />
              <Route path="/clients/:id" element={<ClientDetail />} />
              <Route path="/orders" element={<Orders />} />
              <Route path="/scripts" element={<Scripts />} />
              <Route path="/creators" element={<Creators />} />
              <Route path="/shoots" element={<Shoots />} />
              <Route path="/videos" element={<Videos />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/tickets" element={<Tickets />} />
              <Route path="/employees" element={<Employees />} />
              <Route path="/financials" element={<Financials />} />
              <Route path="/settings" element={<Settings />} />
            </Route>

            {/* Isolated client portal */}
            <Route
              element={
                <ProtectedRoute allow={[ROLES.CLIENT]}>
                  <PortalLayout />
                </ProtectedRoute>
              }
            >
              <Route path="/portal" element={<PortalDashboard />} />
              <Route path="/portal/scripts" element={<PortalScripts />} />
              <Route path="/portal/videos" element={<PortalVideos />} />
              <Route path="/portal/billing" element={<PortalBilling />} />
            </Route>

            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  );
}
