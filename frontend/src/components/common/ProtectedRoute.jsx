import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { ROLES } from '../../data/mockData';

// allow: array of roles permitted. Omit to allow any authenticated user.
export default function ProtectedRoute({ children, allow }) {
  const { user, ready } = useAuth();

  if (!ready) return null;
  if (!user) return <Navigate to="/login" replace />;

  if (allow && !allow.includes(user.role)) {
    return <Navigate to={user.role === ROLES.CLIENT ? '/portal' : '/dashboard'} replace />;
  }
  return children;
}
