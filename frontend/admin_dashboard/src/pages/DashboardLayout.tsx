import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT, LanguageToggle } from '../lib/i18n';
import NavIcon from '../components/common/NavIcon';
import { ALL_NAV_PATHS, NAV_ITEMS, OVERVIEW } from './navigation';
import type { NavItem } from './navigation';

/**
 * The number on a sidebar row.
 *
 * Only ever shows work that is WAITING — an admission nobody has processed, a
 * class whose attendance nobody has taken. A badge counting things already in
 * hand never reaches zero, and a badge that never reaches zero is wallpaper.
 *
 * Caps at 99+ so an institution having a busy week cannot widen the sidebar.
 */
function NavBadge({ count }: { count: number }) {
  if (!count) return null;
  return (
    <span className="ml-auto min-w-[20px] shrink-0 rounded-full bg-red-500 px-1.5 text-center text-[11px] font-semibold leading-5 text-white">
      {count > 99 ? '99+' : count}
    </span>
  );
}

/**
 * Waiting work, by nav path.
 *
 * Phase 1 adds `GET /api/dashboard/badge-counts/` and this polls it on an
 * interval, refreshing on tab focus — Awliaa's pattern, and the same one
 * `docs/08` D8 chose for the activity feed over WebSockets. Until the modules
 * that produce the counts exist there is nothing to poll, and inventing a
 * request that 404s every sixty seconds would fill the console and the server
 * log for no one's benefit.
 */
function useNavBadges(): Record<string, number> {
  return useMemo(() => ({}), []);
}

/**
 * Which institution the platform admin is looking at.
 *
 * Only rendered when `user.branch === null`, because that is the only case
 * where it does anything: `BranchScopeMiddleware` ignores `?branch=` for a user
 * tied to an institution (`docs/02` §3), so showing this to a principal would
 * be a control that silently has no effect.
 */
function BranchSwitcher({ className = '' }: { className?: string }) {
  const { t } = useT();
  const { branches, activeBranchId, setActiveBranchId } = useAuth();

  if (branches.length === 0) return null;

  return (
    <label className={`flex min-w-0 items-center gap-2 ${className}`}>
      <span className="sr-only">{t('Switch institution')}</span>
      <select
        value={activeBranchId ?? ''}
        onChange={(e) => setActiveBranchId(e.target.value ? Number(e.target.value) : null)}
        className="min-h-[44px] w-full min-w-0 truncate rounded-lg border border-gray-200 bg-white px-2 text-base text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        title={t('Viewing institution')}
      >
        <option value="">{t('All institutions (platform view)')}</option>
        {branches.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name_bn || b.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function DashboardLayout() {
  const { t } = useT();
  const { user, logout, branches, activeBranchId } = useAuth();
  const { canView } = usePermissions();
  const location = useLocation();
  const badges = useNavBadges();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const drawerButtonRef = useRef<HTMLButtonElement>(null);

  // The platform admin is the operator of SIES; everybody else belongs to one
  // institution (`docs/08` D1).
  const isPlatformAdmin = user?.branch === null;

  /** Which nav item is showing.
   *
   *  Longest prefix wins, not first match: `/students` and
   *  `/students/admissions` both prefix the admissions URL, and a plain
   *  `startsWith` would light up All students while the user is on Admissions. */
  const activePath = useMemo(() => {
    const matches = ALL_NAV_PATHS.filter(
      (p) => location.pathname === p || (p !== '/' && location.pathname.startsWith(`${p}/`)),
    );
    if (matches.length === 0) return null;
    return matches.reduce((a, b) => (b.length > a.length ? b : a));
  }, [location.pathname]);

  // Close on route change. Without this the drawer stays open over the screen
  // the user just chose, which on a phone hides the whole thing they asked for.
  //
  // Adjusted during render rather than in an effect: an effect would paint the
  // open drawer over the new screen for a frame first, and React re-runs this
  // render immediately without ever showing the discarded output.
  const currentUrl = location.pathname + location.search;
  const [lastUrl, setLastUrl] = useState(currentUrl);
  if (lastUrl !== currentUrl) {
    setLastUrl(currentUrl);
    setDrawerOpen(false);
    setUserMenuOpen(false);
  }

  // Escape closes the drawer and returns focus to the button that opened it,
  // so a keyboard user is not dropped at the top of the document.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setDrawerOpen(false);
        drawerButtonRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  // The page behind must not scroll while the drawer covers it.
  useEffect(() => {
    document.body.style.overflow = drawerOpen ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [drawerOpen]);

  /** The rows this person may actually open. Gated here as well as on the
   *  screen itself, so the sidebar never offers a 403. */
  const visibleItems: NavItem[] = useMemo(
    () =>
      NAV_ITEMS.filter(
        (i) =>
          (!i.platformOnly || isPlatformAdmin) &&
          // A teacher-only row is hidden from everybody else rather than shown
          // empty — see `NavItem.teacherOnly`.
          (!i.teacherOnly || user?.user_type === 'teacher') &&
          canView(i.resource),
      ),
    [canView, isPlatformAdmin, user],
  );

  /* The heading has to follow the switcher, not the account.
   *
   * `user.branch_name` is the right answer for someone tied to an institution,
   * and it is EMPTY for a platform admin — whose branch is null by definition
   * (`docs/01` §5.2). Reading only that field meant the header said "All
   * institutions" no matter which institution the switcher had selected, so
   * every screen below it showed one institution's figures under a heading
   * claiming to show all of them. */
  const selectedBranch =
    activeBranchId == null ? undefined : branches.find((b) => b.id === activeBranchId);
  const institutionName =
    user?.branch_name
    || (selectedBranch && (selectedBranch.name_bn || selectedBranch.name))
    || t('All institutions (platform view)');

  const sidebar = (
    <>
      {/* From `lg` the whole column tightens: 224px wide, 8px of padding, no
          gap between items and a 16px icon. The item's own 44px stays at every
          width — these are `<a>`s, and §7a rule 4 has no breakpoint — so the
          pitch comes down from the gap and the padding, not from the target. */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-4 lg:space-y-0 lg:p-2">
        {canView(OVERVIEW.resource) && (
          <Link
            to={OVERVIEW.path}
            onClick={() => setDrawerOpen(false)}
            aria-current={activePath === OVERVIEW.path ? 'page' : undefined}
            className={`flex min-h-[44px] items-center gap-3 rounded-lg px-4 transition-colors lg:gap-2.5 lg:px-2.5 ${
              activePath === OVERVIEW.path
                ? 'bg-blue-100 text-blue-700'
                : 'text-gray-700 hover:bg-gray-100'
            }`}
          >
            <NavIcon name={OVERVIEW.icon} className="h-5 w-5 shrink-0 lg:h-4 lg:w-4" />
            <span className="font-medium">{t(OVERVIEW.label)}</span>
          </Link>
        )}

        {visibleItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            onClick={() => setDrawerOpen(false)}
            aria-current={item.path === activePath ? 'page' : undefined}
            className={`flex min-h-[44px] items-center gap-3 rounded-lg px-4 transition-colors lg:gap-2.5 lg:px-2.5 ${
              item.path === activePath
                ? 'bg-blue-100 text-blue-700'
                : 'text-gray-700 hover:bg-gray-100'
            }`}
          >
            <NavIcon name={item.icon} className="h-5 w-5 shrink-0 lg:h-4 lg:w-4" />
            <span className="min-w-0 flex-1 truncate font-medium">{t(item.label)}</span>
            <NavBadge count={badges[item.path] ?? 0} />
          </Link>
        ))}
      </nav>

      {/* Signing out lives at the foot of the menu rather than in the top bar.
          It is the one control here you never want hit by accident, and the top
          bar is where the everyday actions are. Sitting below the navigation
          also means a phone user sees their own name — the top bar hides it. */}
      <div className="shrink-0 border-t p-3 pb-safe lg:p-2">
        <p className="px-3 pb-1 text-[11px] uppercase tracking-wide text-gray-400">
          {t('Signed in as')}
        </p>
        <p className="truncate px-3 pb-2 text-sm font-medium text-gray-700">
          {user?.name_bn || user?.name}
        </p>
        <button
          onClick={logout}
          className="flex min-h-[44px] w-full items-center gap-3 rounded-lg px-3 text-sm text-gray-700 transition-colors hover:bg-red-50 hover:text-red-700"
        >
          <svg
            className="h-5 w-5 shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          <span>{t('Logout')}</span>
        </button>
      </div>
    </>
  );

  return (
    <div className="min-h-dvh bg-gray-50">
      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-30 border-b bg-white shadow-sm">
        <div className="mx-auto px-3 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between gap-2 lg:h-14">
            {/* min-w-0 is what lets the institution's name actually truncate:
                without it a flex item refuses to shrink below its content, and
                a long madrasah name pushes the header wider than the phone. */}
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <button
                ref={drawerButtonRef}
                onClick={() => setDrawerOpen((v) => !v)}
                className="tap -ml-2 rounded-md text-gray-700 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 lg:hidden"
                aria-label={t('Toggle menu')}
                aria-expanded={drawerOpen}
                aria-controls="sidebar-drawer"
              >
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {drawerOpen ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  )}
                </svg>
              </button>

              <h1 className="min-w-0 truncate text-base font-bold text-gray-900 sm:text-xl">
                {institutionName}
              </h1>
            </div>

            {/* The controls keep their size and the name gives way, rather than
                both fighting for a 360px header. */}
            <div className="flex shrink-0 items-center gap-2">
              {/* The switcher needs room, so on a phone it moves into the
                  drawer rather than being squeezed into the bar. */}
              {isPlatformAdmin && <BranchSwitcher className="hidden max-w-[16rem] lg:flex" />}

              <LanguageToggle className="hidden sm:inline-flex" />

              <div className="relative">
                <button
                  type="button"
                  onClick={() => setUserMenuOpen((v) => !v)}
                  aria-expanded={userMenuOpen}
                  className="tap rounded-full border border-gray-200 bg-gray-50 text-sm font-semibold text-gray-700 hover:bg-gray-100"
                >
                  {user?.photo ? (
                    <img src={user.photo} alt="" className="h-9 w-9 rounded-full object-cover" />
                  ) : (
                    <span className="px-1">{(user?.name || '?').slice(0, 1).toUpperCase()}</span>
                  )}
                </button>

                {userMenuOpen && (
                  <>
                    {/* Click-away. A menu that only closes via its own button is
                        a trap on a phone, where there is no obvious second
                        target. */}
                    <div className="fixed inset-0 z-40" onClick={() => setUserMenuOpen(false)} aria-hidden />
                    <div className="absolute right-0 z-50 mt-2 w-60 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg">
                      <div className="border-b border-gray-100 px-4 py-3">
                        <p className="truncate text-sm font-medium text-gray-900">
                          {user?.name_bn || user?.name}
                        </p>
                        <p className="mt-0.5 text-xs text-gray-500">{user?.phone}</p>
                      </div>
                      <div className="p-3 sm:hidden">
                        <LanguageToggle />
                      </div>
                      <button
                        onClick={logout}
                        className="flex min-h-[44px] w-full items-center px-4 text-left text-sm text-gray-700 hover:bg-red-50 hover:text-red-700"
                      >
                        {t('Logout')}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </nav>

      <div className="relative flex">
        {/* Backdrop for the drawer. Below lg only — above it the sidebar is
            simply part of the page. */}
        {drawerOpen && (
          <div
            className="fixed inset-0 z-30 bg-black bg-opacity-50 lg:hidden"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* ── Sidebar: drawer below lg, fixed column from lg ─────────────── */}
        <aside
          id="sidebar-drawer"
          className={`fixed inset-y-0 left-0 z-40 flex w-[85vw] max-w-xs transform flex-col border-r bg-white
                      transition-transform duration-300 ease-in-out
                      lg:sticky lg:inset-y-auto lg:top-14 lg:z-20 lg:h-[calc(100dvh-3.5rem)] lg:w-56 lg:max-w-none lg:translate-x-0
                      ${drawerOpen ? 'translate-x-0' : '-translate-x-full'}`}
        >
          {/* The drawer overlays the header, so it carries its own — otherwise
              a phone user has no way back without choosing something. */}
          <div className="flex h-16 shrink-0 items-center justify-between border-b px-4 lg:hidden">
            <span className="min-w-0 truncate font-bold text-gray-900">{institutionName}</span>
            <button
              onClick={() => setDrawerOpen(false)}
              className="tap -mr-2 rounded-md text-gray-500 hover:bg-gray-100"
              aria-label={t('Close')}
            >
              <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {isPlatformAdmin && (
            <div className="border-b p-3 lg:hidden">
              <BranchSwitcher />
            </div>
          )}

          {sidebar}
        </aside>

        {/* ── Main ───────────────────────────────────────────────────────── */}
        {/* min-w-0 is load-bearing. A flex item defaults to min-width:auto,
            which means it refuses to shrink below the intrinsic width of its
            content — so one wide table pushes this column past the viewport and
            takes the whole page with it. The table's own overflow-x-auto never
            engages, because its parent is perfectly happy to grow. With min-w-0
            the column stops at the screen edge and the table scrolls inside it,
            which is what every scroll-x in the app was written to expect. */}
        <main className="w-full min-w-0 flex-1 p-4 pb-safe sm:p-5 lg:px-6 lg:py-4">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
