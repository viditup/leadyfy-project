import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Package,
  FileText,
  Sparkles,
  Camera,
  Clapperboard,
  ListChecks,
  LifeBuoy,
  UserSquare2,
  Wallet,
  Settings,
  X,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { ROLES } from '../../data/mockData';

const NAV = [
  {
    label: 'Overview',
    items: [{ to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, roles: [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE] }],
  },
  {
    label: 'Pipeline',
    items: [
      { to: '/clients', label: 'Clients', icon: Users, roles: [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE] },
      { to: '/orders', label: 'Orders & Packages', icon: Package, roles: [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE] },
      { to: '/scripts', label: 'Scripts', icon: FileText, roles: [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE] },
      { to: '/creators', label: 'Creators', icon: Sparkles, roles: [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE] },
      { to: '/shoots', label: 'Shoots', icon: Camera, roles: [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE] },
      { to: '/videos', label: 'Video Pipeline', icon: Clapperboard, roles: [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE] },
    ],
  },
  {
    label: 'Operations',
    items: [
      { to: '/tasks', label: 'Tasks', icon: ListChecks, roles: [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE] },
      { to: '/tickets', label: 'Support Tickets', icon: LifeBuoy, roles: [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE] },
      { to: '/employees', label: 'Employees', icon: UserSquare2, roles: [ROLES.OWNER, ROLES.ADMIN] },
    ],
  },
  {
    label: 'Finance',
    items: [{ to: '/financials', label: 'Financials', icon: Wallet, roles: [ROLES.OWNER, ROLES.ADMIN] }],
  },
  {
    label: 'System',
    items: [{ to: '/settings', label: 'Settings', icon: Settings, roles: [ROLES.OWNER, ROLES.ADMIN, ROLES.EMPLOYEE] }],
  },
];

export default function Sidebar({ open, onClose }) {
  const { user } = useAuth();

  return (
    <>
      {open && <div className="sidebar-backdrop" onClick={onClose} />}
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <span className="mark">L</span>
          <span className="name">
            Leadyfy <span>OS</span>
          </span>
          <button className="icon-btn sidebar-mobile-toggle" style={{ marginLeft: 'auto' }} onClick={onClose} aria-label="Close menu">
            <X size={16} />
          </button>
        </div>
        <nav className="sidebar-nav">
          {NAV.map((group) => {
            const visible = group.items.filter((i) => i.roles.includes(user?.role));
            if (visible.length === 0) return null;
            return (
              <div className="sidebar-group" key={group.label}>
                <div className="sidebar-group-label">{group.label.toUpperCase()}</div>
                {visible.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    onClick={onClose}
                    className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
                  >
                    <item.icon />
                    {item.label}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="tmuted" style={{ fontSize: 11.5 }}>
            Leadyfy OS v1.0 · Frontend prototype
          </div>
        </div>
      </aside>
    </>
  );
}
