# Fonts

**These files are committed and real.** Nothing has to be dropped in at deploy
time, and the app never fetches a font over the network.

| Family | Files | Used for |
|--------|-------|----------|
| **Hind Siliguri** | `HindSiliguri-{400,500,600,700}-{0,1,2}.woff2` | The whole UI. Bangla and Latin in one face. |
| **Amiri** | `Amiri-{400,700}-{0,1,2}.woff2` | Arabic only — an institution's Arabic name on a letterhead, Qur'anic text. |

## Why these two

**Hind Siliguri** is the face the reference admin dashboard uses, so this system
looks like it rather than merely resembling it. It covers Bangla and Latin
properly, which matters because almost every screen mixes them — a student's
name in Bangla beside a Latin admission number.

**Amiri** exists separately because a Bangla face renders Arabic script without
ligatures or correct joining. Arabic needs its own stack, not a fallback inside
`sans`. Reach it with the Tailwind `font-arabic` class.

## Why self-hosted rather than Google Fonts

The reference project links Google Fonts. This one does not, for two reasons:

1. **A printed admission form or fee receipt has to render identically on an
   office machine with no internet.** A madrasah office is exactly the place
   where that machine exists.
2. A CDN request tells a third party who is using this system, on every page
   load.

The cost is ~700 KB in the repo, sliced so it is never all downloaded at once.

## The `-0` / `-1` / `-2` suffixes

Google subsets each face by `unicode-range` — roughly `-0` bengali, `-1`
latin-ext, `-2` latin. The `@font-face` rules in `src/index.css` carry those
ranges, so a page of English text never downloads the Bengali block. Keep the
ranges if you regenerate these; dropping them makes every visitor fetch
everything.

## Regenerating

```bash
curl -sL -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
  AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  "https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&display=swap"
```

The User-Agent matters: without a modern one Google serves TTF instead of
woff2, which is several times larger. Download each `url(...)` from the result,
then copy its `@font-face` block into `src/index.css` with the path rewritten to
`/myadmin/fonts/<file>`.

## A failure worth remembering

The first version of this directory contained only a README, while
`src/index.css` declared faces named `SolaimanLipi`, `Kalpurush` and
`Scheherazade New`. Every rule 404'd, `local()` matched nothing, and the UI
silently fell back to system fonts. Nothing errored — it just looked wrong. If
the type ever looks off again, check that the files named in `index.css` are
actually here.
