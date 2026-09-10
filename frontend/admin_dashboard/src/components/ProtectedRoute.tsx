import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../lib/auth-context';

function Spinner() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="h-12 w-12 animate-spin rounded-full border-b-4 border-t-4 border-blue-600" />
    </div>
  );
}

/**
 * The gate on everything behind a login.
 *
 * `loading` has to be its own branch. Redirecting while the session is still
 * being restored would bounce every reload through /login and back, which
 * looks like being logged out at random.
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner />;

  if (!isAuthenticated) {
    // Where they were going is remembered, so a link to a student's record
    // shared over WhatsApp still lands on that record after signing in.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <>{children}</>;
}

/** The other half: /login is pointless to somebody already signed in. */
export function PublicRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) return <Spinner />;
  if (isAuthenticated) return <Navigate to="/" replace />;

  return <>{children}</>;
}

export default ProtectedRoute;
