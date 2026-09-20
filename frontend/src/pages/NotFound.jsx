import { useNavigate } from 'react-router-dom';
import { Compass } from 'lucide-react';
import Button from '../components/common/Button';

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="state-block" style={{ minHeight: '70vh' }}>
      <span className="state-icon">
        <CompassIcon size={20} />
      </span>
      <h4>Page not found</h4>
      <p>The page you're looking for doesn't exist or may have moved.</p>
      <Button variant="primary" onClick={() => navigate('/dashboard')}>Back to dashboard</Button>
    </div>
  );
}
