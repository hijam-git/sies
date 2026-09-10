import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './lib/auth-context';
import { LanguageProvider } from './lib/i18n';
import { ProtectedRoute, PublicRoute } from './components/ProtectedRoute';
import DashboardLayout from './pages/DashboardLayout';
import DashboardHome from './pages/DashboardHome';
import LoginPage from './pages/LoginPage';
import PhasePlaceholder from './pages/PhasePlaceholder';
import BranchesPage from './pages/BranchesPage';
import SettingsPage from './pages/SettingsPage';
import UsersPage from './pages/UsersPage';
import StudentsPage from './pages/StudentsPage';
import StaffPage from './pages/StaffPage';
import AcademicsPage from './pages/AcademicsPage';
import FeesPage from './pages/FeesPage';
import AccountsPage from './pages/AccountsPage';
import AttendancePage from './pages/AttendancePage';
import ExamsPage from './pages/ExamsPage';
import ReportsPage from './pages/ReportsPage';
import TeacherDashboard from './pages/TeacherDashboard';
import { PLACEHOLDER_ITEMS } from './pages/navigation';
import './App.css';

/**
 * The route table is built FROM the navigation model (`pages/navigation.tsx`),
 * not written out beside it. Two hand-maintained lists of the same paths drift
 * within a phase, and the failure mode is a sidebar entry that 404s.
 *
 * Real now: login, the overview, Institutions, Settings, Users, phase 2's
 * Students, Staff and Academics, and phase 3's Fees and Accounts. Everything
 * else resolves to a placeholder naming the phase that builds it, because a
 * link that quietly goes nowhere reads as a broken product rather than an
 * unfinished one — and a screen stubbed over a backend that does not exist is
 * worse than either.
 */
/**
 * The home screen depends on who signed in.
 *
 * A teacher opening SIES sees their day — today's periods, which are taken and
 * which is live now (`docs/08` D7) — rather than institution-wide numbers they
 * cannot act on. Everybody else gets the overview.
 */
function Home() {
  const { user } = useAuth();
  return user?.user_type === 'teacher' ? <TeacherDashboard /> : <DashboardHome />;
}

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
              <Route index element={<Home />} />

              {/* Phase 1's real screens. Each gates its own data — a typed URL
                  must not be a way past `canView()`, and the sidebar hiding a
                  row is a convenience, not the enforcement. */}
              <Route path="branches" element={<BranchesPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="users" element={<UsersPage />} />

              {/* Phase 2. Same rule as above — each gates its own data, and
                  each tab inside gates its own resource, because the three
                  screens carry six permissions between them. */}
              <Route path="students" element={<StudentsPage />} />
              <Route path="staff" element={<StaffPage />} />
              <Route path="academics" element={<AcademicsPage />} />

              {/* Phase 3. Fees gates `fees.collect` on its own tab — taking
                  money is a bigger decision than seeing what is owed, and the
                  catalogue gives it its own box for that reason. */}
              <Route path="fees" element={<FeesPage />} />
              <Route path="accounts" element={<AccountsPage />} />

              {/* Phase 4 and 5 — attendance is where a teacher's hours go and
                  exams is where a term ends. Each gates its own data, and each
                  tab inside gates its own resource. */}
              <Route path="attendance" element={<AttendancePage />} />
              <Route path="exams" element={<ExamsPage />} />

              {/* Phase 6. Reports read the other modules' list endpoints and
                  sum them here, so the screen exists as soon as those do. */}
              <Route path="reports" element={<ReportsPage />} />

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
