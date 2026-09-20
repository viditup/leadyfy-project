import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import api, { getErrorMessage } from '../services/api';
import { ROLES } from '../data/mockData';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  // On first load, if a token exists, verify it's still valid via /auth/me.
  useEffect(() => {
    const token = localStorage.getItem('leadyfy_token');
    if (!token) {
      setReady(true);
      return;
    }
    api
      .me()
      .then((profile) => {
        setUser(profile);
        localStorage.setItem('leadyfy_user', JSON.stringify(profile));
      })
      .catch(() => {
        localStorage.removeItem('leadyfy_token');
        localStorage.removeItem('leadyfy_user');
        setUser(null);
      })
      .finally(() => setReady(true));
  }, []);

  const login = useCallback(async (email, password) => {
    try {
      const token = await api.login(email, password);
      localStorage.setItem('leadyfy_token', token.access_token);
      // TokenResponse gives role/user_id/full_name; fetch the full profile
      // (id, email, is_active, created_at) right after for a complete user object.
      const profile = await api.me();
      localStorage.setItem('leadyfy_user', JSON.stringify(profile));
      setUser(profile);
      return { success: true, user: profile };
    } catch (err) {
      return { success: false, message: getErrorMessage(err) };
    }
  }, []);

  function logout() {
    localStorage.removeItem('leadyfy_token');
    localStorage.removeItem('leadyfy_user');
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, ready, login, logout, isClient: user?.role === ROLES.CLIENT }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
