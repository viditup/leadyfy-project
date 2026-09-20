import { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { DEMO_CREDENTIALS, ROLES } from '../data/mockData';
import { Field, Input } from '../components/common/Input';
import Button from '../components/common/Button';

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    return <Navigate to={user.role === ROLES.CLIENT ? '/portal' : '/dashboard'} replace />;
  }

  async function doLogin(loginEmail, loginPassword) {
    setError('');
    setSubmitting(true);
    const result = await login(loginEmail, loginPassword);
    setSubmitting(false);
    if (!result.success) {
      setError(result.message || 'Invalid email or password.');
      return;
    }
    navigate(result.user.role === ROLES.CLIENT ? '/portal' : '/dashboard');
  }

  function handleSubmit(e) {
    e.preventDefault();
    doLogin(email, password);
  }

  function loginAs(cred) {
    setEmail(cred.email);
    setPassword(cred.password);
    doLogin(cred.email, cred.password);
  }

  return (
    <div className="login-shell">
      <div className="login-visual">
        <div className="flex gap-10">
          <span className="mark" style={{ background: 'var(--amber)' }}>
            L
          </span>
          <span className="name" style={{ fontSize: 18 }}>
            Leadyfy <span style={{ color: 'var(--amber-text)' }}>OS</span>
          </span>
        </div>
        <div>
          <h1 style={{ fontSize: 32, marginBottom: 14, maxWidth: 420 }}>One workspace for the whole agency lifecycle.</h1>
          <p className="login-pipeline">
            Lead / Client → Onboarding → Package / Order
            <br />
            → Scripting → Creator Match → Shoot
            <br />
            → Editing → Client Review → Revisions
            <br />→ Final Delivery → Payout & Reports
          </p>
        </div>
        <div className="flex gap-8 tmuted" style={{ fontSize: 12 }}>
          <ShieldCheck size={14} /> Role-based access for Owners, Admins, Employees & Clients
        </div>
      </div>

      <div className="login-form-side">
        <div className="login-card">
          <h2 style={{ fontSize: 22, marginBottom: 6 }}>Sign in</h2>
          <p className="muted" style={{ fontSize: 13, marginBottom: 24 }}>
            Connected to the live Leadyfy OS backend.
          </p>

          <form onSubmit={handleSubmit}>
            <Field label="Email" required>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@leadyfy.com" required />
            </Field>
            <Field label="Password" required error={error}>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
            </Field>
            <Button type="submit" variant="primary" className="w-full" loading={submitting} icon={ArrowRight}>
              Sign in
            </Button>
          </form>

          <div className="divider" />

          <p className="tmuted" style={{ fontSize: 11.5, marginBottom: 10 }}>QUICK DEMO LOGIN</p>
          <div className="flex-col gap-8">
            {DEMO_CREDENTIALS.map((u) => (
              <button
                key={u.email}
                type="button"
                disabled={submitting}
                onClick={() => loginAs(u)}
                className="card"
                style={{
                  padding: '10px 14px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  background: 'var(--bg-surface)',
                  textAlign: 'left',
                  width: '100%',
                }}
              >
                <span>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{u.label}</div>
                  <div className="tmuted" style={{ fontSize: 11.5 }}>
                    {u.email}
                  </div>
                </span>
                <span className="badge badge-amber">Use</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
