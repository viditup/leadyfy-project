import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { LayoutDashboard, FileText, Clapperboard, Receipt, LogOut, Menu, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { initialsOf } from '../../utils/format';

const PORTAL_NAV = [
  { to: '/portal', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/portal/scripts', label: 'Scripts', icon: FileText },
  { to: '/portal/videos', label: 'Videos', icon: Clapperboard },
  { to: '/portal/billing', label: 'Billing & Support', icon: Receipt },
];

export default function PortalLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  return (
    <div className="app-shell">
      {open && <div className="sidebar-backdrop" onClick={() => setOpen(false)} />}
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <span className="mark">L</span>
          <span className="name">
            Leadyfy <span>Portal</span>
          </span>
          <button className="icon-btn sidebar-mobile-toggle" style={{ marginLeft: 'auto' }} onClick={() => setOpen(false)}>
            <X size={16} />
          </button>
        </div>
        <nav className="sidebar-nav">
          <div className="sidebar-group">
            <div className="sidebar-group-label">CLIENT PORTAL</div>
            {PORTAL_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setOpen(false)}
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
              >
                <item.icon />
                {item.label}
              </NavLink>
            ))}
          </div>
        </nav>
        <div className="sidebar-footer tmuted" style={{ fontSize: 11.5 }}>
          You're viewing an isolated client workspace — internal costs and other clients are never visible here.
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <button className="icon-btn sidebar-mobile-toggle" onClick={() => setOpen(true)}>
            <Menu size={17} />
          </button>
          <div className="topbar-right" style={{ marginLeft: 'auto' }}>
            <span className="muted" style={{ fontSize: 13 }}>
              {user.full_name}
            </span>
            <span className="avatar">{initialsOf(user.full_name)}</span>
            <button
              className="icon-btn"
              onClick={() => {
                logout();
                navigate('/login');
              }}
              title="Log out"
            >
              <LogOut size={15} />
            </button>
          </div>
        </header>
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
