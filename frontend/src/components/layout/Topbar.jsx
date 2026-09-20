import { useEffect, useRef, useState } from 'react';
import { Menu, Search, Bell, LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { SUB_ROLE_LABELS, humanize } from '../../data/mockData';
import { api } from '../../services/api';
import { initialsOf, formatRelativeTime } from '../../utils/format';

export default function Topbar({ onMenuClick, title }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const popRef = useRef(null);

  function loadNotifications() {
    api.getNotifications().then(setNotifications).catch(() => {});
  }

  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    function onClick(e) {
      if (popRef.current && !popRef.current.contains(e.target)) setNotifOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  async function handleNotifClick(n) {
    if (!n.is_read) {
      try {
        await api.markNotificationRead(n.id);
        setNotifications((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
      } catch {
        /* non-critical */
      }
    }
  }

  async function handleMarkAllRead() {
    try {
      await api.markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch {
      /* non-critical */
    }
  }

  return (
    <header className="topbar">
      <div className="flex gap-12">
        <button className="icon-btn sidebar-mobile-toggle" onClick={onMenuClick} aria-label="Open menu">
          <Menu size={17} />
        </button>
        {title && <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 15, margin: 0 }}>{title}</h2>}
        <div className="search-input topbar-search">
          <Search size={15} />
          <input className="input" placeholder="Search clients, orders, videos…" disabled />
        </div>
      </div>

      <div className="topbar-right">
        <div className="role-pill" title={user.role === 'employee' && user.sub_role ? SUB_ROLE_LABELS[user.sub_role] : humanize(user.role)}>
          <span className="tmuted" style={{ fontSize: 11.5 }}>
            {humanize(user.role)}
          </span>
        </div>

        <div style={{ position: 'relative' }} ref={popRef}>
          <button className="icon-btn notif-btn" onClick={() => setNotifOpen((v) => !v)} aria-label="Notifications">
            <Bell size={16} />
            {unreadCount > 0 && <span className="notif-dot" />}
          </button>
          {notifOpen && (
            <div
              className="card"
              style={{
                position: 'absolute',
                right: 0,
                top: 42,
                width: 340,
                zIndex: 50,
                boxShadow: 'var(--shadow-pop)',
              }}
            >
              <div className="card-header">
                <h3>Notifications</h3>
                {unreadCount > 0 && (
                  <button className="btn btn-ghost btn-sm" onClick={handleMarkAllRead}>
                    Mark all read
                  </button>
                )}
              </div>
              <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                {notifications.length === 0 && (
                  <div style={{ padding: '16px', fontSize: 12.5 }} className="tmuted">
                    No notifications yet.
                  </div>
                )}
                {notifications.map((n) => (
                  <div
                    key={n.id}
                    onClick={() => handleNotifClick(n)}
                    style={{
                      padding: '10px 16px',
                      borderBottom: '1px solid var(--border-soft)',
                      cursor: 'pointer',
                      background: n.is_read ? 'transparent' : 'rgba(245,158,11,0.06)',
                    }}
                  >
                    <div style={{ fontSize: 12.5, fontWeight: n.is_read ? 400 : 600 }}>{n.title}</div>
                    <div style={{ fontSize: 12, marginTop: 2 }} className="tmuted">{n.message}</div>
                    <div className="tmuted" style={{ fontSize: 11, marginTop: 3 }}>
                      {formatRelativeTime(n.created_at)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-8">
          <span className="avatar" title={user.full_name}>{initialsOf(user.full_name)}</span>
          <button className="icon-btn" onClick={() => { logout(); navigate('/login'); }} aria-label="Log out" title="Log out">
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </header>
  );
}
