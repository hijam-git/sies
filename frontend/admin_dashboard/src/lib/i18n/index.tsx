import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { BN } from './dictionary';

export type Lang = 'en' | 'bn';

interface I18nContextType {
  lang: Lang;
  setLang: (l: Lang) => void;
  /** Translate an English source string. In `bn` mode returns the Bangla if
   *  the dictionary has it, else the English text — a missing translation is
   *  a readable screen, not a blank one. */
  t: (en: string) => string;
}

const I18nContext = createContext<I18nContextType | undefined>(undefined);

const STORAGE_KEY = 'sies_admin_lang';

/**
 * Bangla is the default and English is the toggle (`docs/08` §7).
 *
 * Not the browser's `navigator.language`: an office machine in Bangladesh
 * ships with an English locale, so guessing from it would greet every user of
 * this product in the wrong language.
 */
function initialLang(): Lang {
  if (typeof window === 'undefined') return 'bn';
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === 'en' || saved === 'bn' ? saved : 'bn';
  } catch {
    return 'bn';
  }
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // Private browsing, or storage full. Losing the preference on reload is
      // a far smaller problem than refusing to switch language at all.
    }
  }, []);

  // Keeps `:lang()` in index.css and the browser's own hyphenation honest.
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const t = useCallback((en: string) => (lang === 'bn' ? (BN[en] ?? en) : en), [lang]);

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useT(): I18nContextType {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    // A component rendered outside the provider — a unit test, usually —
    // behaves as an English passthrough rather than throwing. A missing
    // translator is not worth failing a render over.
    return { lang: 'en', setLang: () => {}, t: (en: string) => en };
  }
  return ctx;
}

/** The header's language switcher: বাংলা / EN. */
export function LanguageToggle({ className = '' }: { className?: string }) {
  const { lang, setLang } = useT();
  return (
    // A segmented control: a quiet grey track with the chosen language as a
    // raised white chip. The old solid-blue half drew the eye harder than
    // anything else in the header, for the control people touch least.
    <div
      className={`inline-flex h-8 items-center gap-0.5 rounded-lg bg-gray-100 p-0.5 text-xs font-semibold ${className}`}
    >
      {(['bn', 'en'] as const).map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          className={`flex h-7 min-w-[40px] items-center justify-center rounded-md px-2.5 transition-all ${
            lang === code
              ? 'bg-white text-gray-900 shadow-sm ring-1 ring-gray-900/5'
              : 'text-gray-500 hover:text-gray-800'
          }`}
        >
          {code === 'bn' ? 'বাংলা' : 'EN'}
        </button>
      ))}
    </div>
  );
}
