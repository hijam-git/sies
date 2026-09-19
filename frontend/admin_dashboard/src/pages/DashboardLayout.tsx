import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAuth, usePermissions } from '../lib/auth-context';
import ChangePasswordModal from '../components/account/ChangePasswordModal';
import { useT, LanguageToggle } from '../lib/i18n';
import NavIcon from '../components/common/NavIcon';
import { ALL_NAV_PATHS, NAV_ITEMS, OVERVIEW } from './navigation';
import type { NavChild, NavItem } from './navigation';

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
    <label className={`relative flex min-w-0 items-center ${className}`}>
      <span className="sr-only">{t('Switch institution')}</span>
      <svg
        className="pointer-events-none absolute left-2.5 h-4 w-4 text-gray-400"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        viewBox="0 0 24 24"
        aria-hidden
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 21h18M5 21V7l7-4 7 4v14M9 9h1m4 0h1M9 13h1m4 0h1M10 21v-4h4v4" />
      </svg>
      <select
        value={activeBranchId ?? ''}
        onChange={(e) => setActiveBranchId(e.target.value ? Number(e.target.value) : null)}
        className="h-10 w-full min-w-0 truncate rounded-lg border border-gray-200 bg-white pl-8 pr-8 text-base text-gray-800 transition-colors hover:border-gray-300 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30 lg:h-8 lg:text-[13px]"
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

/* One sidebar row. 36px on a phone, 32px from `lg`, 13px text — compact, the
   way the rest of the panel's controls are (`components/common/styles.ts`). */
const rowCls =
  'flex min-h-[36px] items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium transition-colors lg:min-h-[32px]';
const rowActiveCls = 'bg-blue-50 text-blue-700';
const rowIdleCls = 'text-gray-700 hover:bg-gray-100 hover:text-gray-900';

export default function DashboardLayout() {
  const { t } = useT();
  const { user, logout, branches, activeBranchId } = useAuth();
  const { can, canView } = usePermissions();
  const location = useLocation();
  const badges = useNavBadges();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  /** Opened from the user menu, and forced open below when the account is
   *  still on the password an admin handed over. */
  const [changingPassword, setChangingPassword] = useState(false);
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

  /** Which group is expanded.
   *
   *  The active section's group is open by default, so landing on
   *  `/fees?tab=dues` shows where you are without a click. An explicit toggle
   *  wins — `''` means the reader closed everything — and is dropped again on
   *  the next navigation, so the menu follows the reader instead of remembering
   *  a choice about a page they have left. Derived rather than written from an
   *  effect (`CLAUDE.md` §7b). */
  const [openChoice, setOpenChoice] = useState<string | null>(null);
  const openGroup = openChoice ?? activePath;

  /** The tab the page is showing, for highlighting a sub-item. No `?tab=` is
   *  the page's default, which is its first tab this reader may open. */
  const activeTab = new URLSearchParams(location.search).get('tab');

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
    setOpenChoice(null);
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
          (i.anyResource ? i.anyResource.some((r) => canView(r)) : canView(i.resource)),
      ),
    [canView, isPlatformAdmin, user],
  );

  /** A group's sub-items this reader may open — the same gates the page uses
   *  to build its own tab strip. */
  const childrenOf = (item: NavItem): NavChild[] =>
    (item.children ?? []).filter(
      (c) => !c.anyOf || c.anyOf.some(([resource, action]) => can(resource, action)),
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
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-3 lg:p-2">
        {canView(OVERVIEW.resource) && (
          <Link
            to={OVERVIEW.path}
            onClick={() => setDrawerOpen(false)}
            aria-current={activePath === OVERVIEW.path ? 'page' : undefined}
            className={`${rowCls} ${activePath === OVERVIEW.path ? rowActiveCls : rowIdleCls}`}
          >
            <NavIcon name={OVERVIEW.icon} className="h-[18px] w-[18px] shrink-0 lg:h-4 lg:w-4" />
            <span>{t(OVERVIEW.label)}</span>
          </Link>
        )}

        {visibleItems.map((item) => {
          const kids = childrenOf(item);
          const isActive = item.path === activePath;

          // One view (or one the reader may open): a plain link, no group.
          if (kids.length < 2) {
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setDrawerOpen(false)}
                aria-current={isActive ? 'page' : undefined}
                className={`${rowCls} ${isActive ? rowActiveCls : rowIdleCls}`}
              >
                <NavIcon name={item.icon} className="h-[18px] w-[18px] shrink-0 lg:h-4 lg:w-4" />
                <span className="min-w-0 flex-1 truncate">{t(item.label)}</span>
                <NavBadge count={badges[item.path] ?? 0} />
              </Link>
            );
          }

          const expanded = openGroup === item.path;
          const groupId = `nav-group-${item.path.slice(1)}`;
          return (
            <div key={item.path}>
              {/* The parent only opens and closes. Making it a link as well
                  would mean the one row that shows the choices also takes you
                  away before you have seen them. */}
              <button
                type="button"
                onClick={() => setOpenChoice(expanded ? '' : item.path)}
                aria-expanded={expanded}
                aria-controls={groupId}
                className={`${rowCls} w-full text-left ${
                  isActive ? 'text-blue-700' : rowIdleCls
                }`}
              >
                <NavIcon name={item.icon} className="h-[18px] w-[18px] shrink-0 lg:h-4 lg:w-4" />
                <span className="min-w-0 flex-1 truncate">{t(item.label)}</span>
                <NavBadge count={badges[item.path] ?? 0} />
                <svg
                  className={`h-3.5 w-3.5 shrink-0 text-gray-400 transition-transform duration-200 ${
                    expanded ? 'rotate-90' : ''
                  }`}
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden
                >
                  <path
                    fillRule="evenodd"
                    d="M7.21 14.77a.75.75 0 01.02-1.06L11.17 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>

              {expanded && (
                <ul id={groupId} className="mb-1 ml-[21px] space-y-px border-l border-gray-200 pl-2 lg:ml-[17px]">
                  {kids.map((kid, index) => {
                    // The first tab this reader may open is the page's default,
                    // which the page keeps out of the URL — so it links to the
                    // bare path and is active when there is no `?tab=`.
                    const isDefault = index === 0;
                    const kidActive =
                      isActive && (activeTab === kid.tab || (isDefault && !activeTab));
                    return (
                      <li key={kid.tab}>
                        <Link
                          to={isDefault ? item.path : `${item.path}?tab=${kid.tab}`}
                          onClick={() => setDrawerOpen(false)}
                          aria-current={kidActive ? 'page' : undefined}
                          className={`flex min-h-[34px] items-center rounded-md px-2.5 text-[13px] transition-colors lg:min-h-[30px] ${
                            kidActive
                              ? 'bg-blue-50 font-semibold text-blue-700'
                              : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                          }`}
                        >
                          <span className="min-w-0 truncate">{t(kid.label)}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}
      </nav>

      {/* No sign-out foot here: it lives in the account menu behind the avatar
          in the top bar, which carries the name and phone as well. */}
    </>
  );

  return (
    <>
    <div className="min-h-dvh bg-gray-50">
      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      {/* One 56px bar at every width. The left block is exactly the sidebar's
          width from `lg`, so the brand sits over the menu it belongs to and the
          institution's name starts where the page starts — two columns, read as
          two columns. Translucent with a blur so a scrolled table shows through
          as movement rather than being cut off by a hard white slab. */}
      <header id="app-topbar" className="sticky top-0 z-30 border-b border-gray-200/80 bg-white/90 backdrop-blur supports-[backdrop-filter]:bg-white/75">
        <div className="flex h-14 items-center gap-2 pr-3 sm:pr-5 lg:pr-6">
          <div className="flex h-full shrink-0 items-center gap-1 pl-2 sm:pl-3 lg:w-56 lg:border-r lg:border-gray-200/80 lg:pl-4">
            <button
              ref={drawerButtonRef}
              onClick={() => setDrawerOpen((v) => !v)}
              className="tap rounded-md text-gray-600 hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 lg:hidden"
              aria-label={t('Toggle menu')}
              aria-expanded={drawerOpen}
              aria-controls="sidebar-drawer"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                {drawerOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M4 12h16M4 17h10" />
                )}
              </svg>
            </button>

            <Link to="/" className="flex items-center gap-2 rounded-md pr-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-sm shadow-blue-600/30">
                <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.25v13m0-13C10.83 5.48 9.25 5 7.5 5S4.17 5.48 3 6.25v13C4.17 18.48 5.75 18 7.5 18s3.33.48 4.5 1.25m0-13C13.17 5.48 14.75 5 16.5 5s3.33.48 4.5 1.25v13C19.83 18.48 18.25 18 16.5 18s-3.33.48-4.5 1.25" />
                </svg>
              </span>
              {/* The product name only where there is room for it beside the
                  institution's; on a phone the institution is the one that
                  matters. */}
              <span className="hidden text-[15px] font-bold tracking-tight text-gray-900 lg:inline">SIES</span>
            </Link>
          </div>

          {/* min-w-0 is what lets the name truncate: a flex item otherwise
              refuses to shrink below its content, and a long madrasah name
              pushes the header wider than the phone. */}
          <div className="min-w-0 flex-1 lg:pl-4">
            <h1 className="truncate text-sm font-semibold text-gray-900 sm:text-[15px]">
              {institutionName}
            </h1>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {/* The switcher needs room, so on a phone it moves into the drawer
                rather than being squeezed into the bar. */}
            {isPlatformAdmin && <BranchSwitcher className="hidden w-60 lg:flex" />}

            <LanguageToggle className="hidden sm:inline-flex" />

            <span className="hidden h-5 w-px bg-gray-200 sm:block" aria-hidden />

            <div className="relative">
              <button
                type="button"
                onClick={() => setUserMenuOpen((v) => !v)}
                aria-expanded={userMenuOpen}
                aria-haspopup="menu"
                className="flex h-9 items-center gap-2 rounded-lg pl-1 pr-1 transition-colors hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 md:pr-2"
              >
                {user?.photo ? (
                  <img src={user.photo} alt="" className="h-7 w-7 rounded-full object-cover ring-1 ring-gray-900/5" />
                ) : (
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-slate-600 to-slate-800 text-xs font-semibold text-white">
                    {(user?.name || '?').slice(0, 1).toUpperCase()}
                  </span>
                )}
                <span className="hidden max-w-[10rem] truncate text-[13px] font-medium text-gray-700 md:block">
                  {user?.name_bn || user?.name}
                </span>
                <svg
                  className={`hidden h-3.5 w-3.5 text-gray-400 transition-transform md:block ${userMenuOpen ? 'rotate-180' : ''}`}
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden
                >
                  <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                </svg>
              </button>

              {userMenuOpen && (
                <>
                  {/* Click-away. A menu that only closes via its own button is a
                      trap on a phone, where there is no obvious second target. */}
                  <div className="fixed inset-0 z-40" onClick={() => setUserMenuOpen(false)} aria-hidden />
                  <div
                    role="menu"
                    className="absolute right-0 z-50 mt-2 w-64 overflow-hidden rounded-xl border border-gray-200/80 bg-white shadow-xl shadow-gray-900/10"
                  >
                    <div className="flex items-center gap-3 px-4 py-3">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-slate-600 to-slate-800 text-sm font-semibold text-white">
                        {(user?.name || '?').slice(0, 1).toUpperCase()}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-semibold text-gray-900">
                          {user?.name_bn || user?.name}
                        </p>
                        <p className="truncate font-mono text-xs text-gray-500">{user?.phone}</p>
                      </div>
                    </div>
                    <div className="border-t border-gray-100 px-4 py-2.5 sm:hidden">
                      <LanguageToggle />
                    </div>
                    <div className="border-t border-gray-100 p-1.5">
                      <button
                        role="menuitem"
                        onClick={() => {
                          setUserMenuOpen(false);
                          setChangingPassword(true);
                        }}
                        className="flex h-9 w-full items-center gap-2.5 rounded-md px-2.5 text-left text-[13px] font-medium text-gray-700 transition-colors hover:bg-gray-50"
                      >
                        <svg className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                        </svg>
                        {t('Change password')}
                      </button>
                      <button
                        role="menuitem"
                        onClick={logout}
                        className="flex h-9 w-full items-center gap-2.5 rounded-md px-2.5 text-left text-[13px] font-medium text-gray-700 transition-colors hover:bg-red-50 hover:text-red-700"
                      >
                        <svg className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                        </svg>
                        {t('Logout')}
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

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
          <div className="flex h-14 shrink-0 items-center justify-between border-b border-gray-200/80 px-4 lg:hidden">
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

      {/* Every account an admin creates carries `must_change_password`, because
          the password was said out loud to hand it over. Nothing enforced it:
          the endpoint had no caller and no screen offered it, so every
          temporary password stayed live. Forced, this modal has no way out. */}
      {(changingPassword || user?.must_change_password) && (
        <ChangePasswordModal
          forced={!changingPassword && !!user?.must_change_password}
          onClose={() => setChangingPassword(false)}
        />
      )}
    </>
  );
}
