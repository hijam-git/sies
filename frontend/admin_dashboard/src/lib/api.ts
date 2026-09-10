/**
 * The one way this dashboard talks to the backend.
 *
 * Everything goes through `ApiClient.request`, which injects the JWT, retries
 * once behind a refresh on 401, and turns the API's single error shape into an
 * `ApiError`. Screens never call `fetch` themselves — a second call site is a
 * second place for a 401 to log somebody out at random.
 */

// Runtime API URL from window.ENV, written by the container at start rather
// than baked into the bundle. It is what lets one built image be promoted from
// staging to production: rebuilding to change a URL means the thing that was
// tested is not the thing that ships.
declare global {
  interface Window {
    ENV?: {
      API_URL?: string;
    };
  }
}

const getApiUrl = (): string => {
  return (typeof window !== 'undefined' && window.ENV?.API_URL) || '/api';
};

// ── Domain types ──────────────────────────────────────────────────────────

/** Who the person is. `docs/02` §1. */
export type UserType =
  | 'platform_admin'
  | 'platform_accountant'
  | 'principal'
  | 'accountant'
  | 'teacher'
  | 'employee'
  | 'student';

export type Language = 'bn' | 'en';

/** What kind of institution a branch is. Selects the seeded streams, classes
 *  and form template, and the labels the UI uses (`docs/08` D1). */
export type InstitutionType = 'madrasah' | 'school' | 'college' | 'combined';

/**
 * A branch is a whole institution — a school, a madrasah or a college — and
 * SIES is the platform they run on (`docs/08` D1). The word "branch" is kept
 * because it is the owner's word and renaming it later is churn.
 */
export interface Branch {
  id: number;
  name: string;
  name_bn: string;
  name_ar: string;
  code: string;
  institution_type: InstitutionType;
  address: string;
  phone: string;
  email: string;
  logo: string | null;
  established_year: number | null;
  is_active: boolean;
}

export interface User {
  id: number;
  /** 11 digits, canonical form (01712345678). The only login identifier there
   *  is — see `normalizeBdPhone`. */
  phone: string;
  name: string;
  name_bn: string;
  user_type: UserType;
  /** `null` means the platform admin, who is not tied to one institution and
   *  is the only user allowed to switch between them (`docs/02` §3). */
  branch: Branch | null;
  /**
   * The permissions the SERVER resolved for this person: their own list if an
   * admin has ever customised it, otherwise their role's preset — never the
   * two merged (`docs/02` §2.3). Empty means the role preset is being used and
   * the backend did not expand it; `lib/permissions.ts` falls back the same way.
   */
  permissions: string[];
  /** The preset this account sits on, so the permission screen can show what
   *  its boxes would be before an admin customises them. */
  role: string | null;
  language: Language;
  photo: string | null;
  is_active: boolean;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  user: User;
}

/**
 * The one error shape the whole API answers with, from the copied exception
 * handler (`CLAUDE.md` §3.2). `code` is a stable snake_case identifier for us;
 * `message` is the sentence written for the person reading the screen.
 */
export interface ApiErrorBody {
  success: false;
  message: string;
  /** Field-level validation, `{ phone: ["..."] }`. Absent for non-form errors. */
  errors?: Record<string, string[]>;
  code?: string;
}

/** A DRF page. Every list endpoint is paginated (`CLAUDE.md` §5). */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export class ApiError extends Error {
  status: number;
  /** The stable identifier — `fee_already_paid`, not a sentence. */
  code: string | null;
  errors: Record<string, string[]> | null;

  constructor(status: number, message: string, body?: Partial<ApiErrorBody>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body?.code ?? null;
    this.errors = body?.errors ?? null;
  }
}

// ── Storage keys ──────────────────────────────────────────────────────────
// One place, because a key typed twice is a logout that only happens on
// Tuesdays.
const ACCESS_KEY = 'sies_access_token';
const REFRESH_KEY = 'sies_refresh_token';
const USER_KEY = 'sies_user';
const BRANCH_KEY = 'sies_active_branch';

class ApiClient {
  getBaseUrl(): string {
    return getApiUrl();
  }

  private getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  }

  private getAuthHeaders(): Record<string, string> {
    const token = this.getAccessToken();
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }

  private setTokens(access: string, refresh: string): void {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  }

  private clearTokens(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(BRANCH_KEY);
  }

  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }

  getStoredUser(): User | null {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      // A half-written or older-shaped value must not wedge the app on a blank
      // screen every time it loads.
      localStorage.removeItem(USER_KEY);
      return null;
    }
  }

  // ── Branch selection (platform admin only) ──────────────────────────────
  // `BranchScopeMiddleware` reads `?branch=` and IGNORES it for anyone whose
  // own `user.branch` is set (`docs/02` §3), so sending it always is safe: an
  // institution's own principal cannot widen their scope with a copied URL.

  getActiveBranchId(): number | null {
    const raw = localStorage.getItem(BRANCH_KEY);
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) ? n : null;
  }

  setActiveBranchId(id: number | null): void {
    if (id === null) localStorage.removeItem(BRANCH_KEY);
    else localStorage.setItem(BRANCH_KEY, String(id));
  }

  private withBranch(endpoint: string): string {
    const id = this.getActiveBranchId();
    if (id === null) return endpoint;
    return endpoint + (endpoint.includes('?') ? '&' : '?') + `branch=${id}`;
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (response.status === 204 || response.headers.get('content-length') === '0') {
      return undefined as T;
    }

    const body: unknown = await response.json().catch(() => null);

    if (!response.ok) {
      const err = (body ?? {}) as Partial<ApiErrorBody>;
      // The backend's handler always fills `message`. The status-line fallback
      // is for the two cases it cannot reach: a proxy error page, and a
      // response that was not JSON at all.
      throw new ApiError(
        response.status,
        err.message || `${response.status} ${response.statusText}`,
        err,
      );
    }

    return body as T;
  }

  // Single-flight lock: with ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION
  // on, concurrent 401s (a data-heavy page fires many calls at once) would each
  // refresh with the SAME old token; the first succeeds and blacklists it, the
  // rest 401 → clearTokens → random logouts. All concurrent callers must share
  // ONE in-flight refresh.
  private refreshPromise: Promise<boolean> | null = null;

  private refreshAccessToken(): Promise<boolean> {
    if (this.refreshPromise) return this.refreshPromise;
    this.refreshPromise = this.doRefresh().finally(() => {
      this.refreshPromise = null;
    });
    return this.refreshPromise;
  }

  private async doRefresh(): Promise<boolean> {
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (!refresh) return false;

    try {
      const response = await fetch(`${this.getBaseUrl()}/auth/token/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
      });

      if (response.ok) {
        const data = (await response.json()) as { access: string; refresh?: string };
        localStorage.setItem(ACCESS_KEY, data.access);
        // ROTATE_REFRESH_TOKENS blacklists the one we just sent — keep the new.
        if (data.refresh) localStorage.setItem(REFRESH_KEY, data.refresh);
        return true;
      }
    } catch {
      // Offline, or the backend is restarting. Falling through clears the
      // tokens, which sends the user to /login — the honest outcome either way.
    }

    this.clearTokens();
    return false;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.getBaseUrl()}${this.withBranch(endpoint)}`;
    const send = () =>
      fetch(url, {
        ...options,
        headers: { ...this.getAuthHeaders(), ...options.headers },
      });

    let response = await send();

    if (response.status === 401 && this.getAccessToken()) {
      if (await this.refreshAccessToken()) response = await send();
    }

    return this.handleResponse<T>(response);
  }

  /** Multipart upload. No Content-Type header — the browser must set the
   *  boundary, and naming the type ourselves strips it. */
  private async upload<T>(
    endpoint: string,
    file: File,
    field = 'file',
    extra?: Record<string, string>,
  ): Promise<T> {
    const form = new FormData();
    form.append(field, file);
    for (const [k, v] of Object.entries(extra ?? {})) form.append(k, v);

    const send = () =>
      fetch(`${this.getBaseUrl()}${this.withBranch(endpoint)}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${this.getAccessToken()}` },
        body: form,
      });

    let response = await send();
    if (response.status === 401 && this.getAccessToken()) {
      if (await this.refreshAccessToken()) response = await send();
    }
    return this.handleResponse<T>(response);
  }

  /** Escape hatch for callers that need a raw response — a CSV download, a
   *  printable PDF. Same token handling, no JSON parsing. */
  async fetchRaw(endpoint: string, options: RequestInit = {}): Promise<Response> {
    const url = `${this.getBaseUrl()}${this.withBranch(endpoint)}`;
    const send = () =>
      fetch(url, {
        ...options,
        headers: {
          Authorization: `Bearer ${this.getAccessToken()}`,
          ...options.headers,
        },
      });

    let response = await send();
    if (response.status === 401 && this.getAccessToken()) {
      if (await this.refreshAccessToken()) response = await send();
    }
    return response;
  }

  // ── Authentication ──────────────────────────────────────────────────────

  /** Phone + password. There is no other way in: no email login, no OAuth. */
  async login(phone: string, password: string): Promise<LoginResponse> {
    const response = await this.request<LoginResponse>('/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ phone, password }),
    });

    this.setTokens(response.access, response.refresh);
    localStorage.setItem(USER_KEY, JSON.stringify(response.user));
    return response;
  }

  async logout(): Promise<void> {
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (refresh) {
      try {
        await this.request('/auth/logout/', {
          method: 'POST',
          body: JSON.stringify({ refresh }),
        });
      } catch {
        // Blacklisting the token server-side is a courtesy. Failing to do it
        // must never leave somebody logged in on a shared office machine.
      }
    }
    this.clearTokens();
  }

  /** The signed-in user, re-read on boot so a permission change made while
   *  they were away takes effect on their next load rather than their next
   *  login. Returns null when the session is gone. */
  async getCurrentUser(): Promise<User | null> {
    try {
      const user = await this.request<User>('/auth/me/');
      localStorage.setItem(USER_KEY, JSON.stringify(user));
      return user;
    } catch {
      return null;
    }
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await this.request('/auth/change-password/', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  }

  async updateMyLanguage(language: Language): Promise<User> {
    const user = await this.request<User>('/auth/me/', {
      method: 'PATCH',
      body: JSON.stringify({ language }),
    });
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    return user;
  }

  async uploadMyPhoto(file: File): Promise<User> {
    return this.upload<User>('/auth/me/photo/', file, 'photo');
  }

  // ── Branches ────────────────────────────────────────────────────────────

  /** Every institution the caller may see. For a platform admin that is all of
   *  them, which is what the header's branch switcher lists; for anyone else
   *  the backend returns their own and nothing more. */
  async getBranches(): Promise<Branch[]> {
    const page = await this.request<Paginated<Branch>>('/branches/');
    return page.results;
  }
}

export const apiClient = new ApiClient();
