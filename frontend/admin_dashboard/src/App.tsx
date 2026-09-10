import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './lib/auth-context';
import { LanguageProvider } from './lib/i18n';
import { ProtectedRoute, PublicRoute } from './components/ProtectedRoute';
import DashboardLayout from './pages/DashboardLayout';
import DashboardHome from './pages/DashboardHome';
import LoginPage from './pages/LoginPage';
import PhasePlaceholder from './pages/PhasePlaceholder';
import { PLACEHOLDER_ITEMS } from './pages/navigation';
import './App.css';

/**
 * The route table is built FROM the navigation model (`pages/navigation.tsx`),
 * not written out beside it. Two hand-maintained lists of the same paths drift
 * within a phase, and the failure mode is a sidebar entry that 404s.
 *
 * Only two screens are real in phase 0 — login and the overview. Every other
 * nav item resolves to a placeholder naming the phase that builds it, because
 * a link that quietly goes nowhere reads as a broken product rather than an
 * unfinished one.
 */
function App() {
  return (
    // The SPA is served under /myadmin and Traefik routes it there. Changing
    // this means changing the proxy, the Vite `base` and every bookmark.
    <BrowserRouter basename="/myadmin">
      {/* Language wraps auth because AuthProvider adopts the signed-in user's
          saved language as soon as it knows who they are. */}
      <LanguageProvider>
        <AuthProvider>
          <Routes>
            <Route
              path="/login"
              element={
                <PublicRoute>
                  <LoginPage />
                </PublicRoute>
              }
            />

            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <DashboardLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<DashboardHome />} />
              {PLACEHOLDER_ITEMS.map((item) => (
                <Route
                  key={item.path}
                  // Relative, because these are nested under the layout's "/".
                  path={item.path.replace(/^\//, '')}
                  element={<PhasePlaceholder labelKey={item.label} phase={item.phase} />}
                />
              ))}
            </Route>

            {/* Anything else — a stale bookmark, a typo — goes home rather than
                to a blank screen. */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </LanguageProvider>
    </BrowserRouter>
  );
}

export default App;
