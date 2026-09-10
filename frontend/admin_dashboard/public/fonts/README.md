# Fonts — drop the binaries here

The dashboard **never loads a font over the network.** Printed admission forms,
fee receipts and mark sheets have to come out identically on an office machine
with no internet, and a Google Fonts request would also report every visit to a
third party. So the faces are self-hosted from this directory and declared with
`@font-face` in `src/index.css`.

These files are **not committed** — they carry their own licences and are large
binaries. Put them here before building an image, and add the directory to your
deployment's asset step.

## Files `src/index.css` expects

| File | Face | Used for |
|------|------|----------|
| `SolaimanLipi.woff2` | SolaimanLipi, regular (400) | Bangla body text — the whole UI |
| `SolaimanLipi-Bold.woff2` | SolaimanLipi, bold (700) | Bangla headings and table headers |
| `Kalpurush.woff2` | Kalpurush, regular (400) | Bangla fallback — a second opinion on conjuncts SolaimanLipi renders tightly |
| `Amiri-Regular.woff2` | Amiri, regular (400) | Arabic — Qur'anic lines, du'a, an institution's Arabic name |
| `Amiri-Bold.woff2` | Amiri, bold (700) | Arabic headings |
| `ScheherazadeNew-Regular.woff2` | Scheherazade New, regular (400) | Arabic fallback — larger on the line, better for a printed form a child reads |

A missing file is **not** a broken page: every `@font-face` sits at the front of
a stack that ends in `Noto Sans Bengali` / `Noto Naskh Arabic` and then the
system UI font (`tailwind.config.js`). The page degrades to whatever the machine
has rather than to Times New Roman with broken conjuncts.

## Where to get them

| Face | Source | Licence |
|------|--------|---------|
| SolaimanLipi | <https://www.omicronlab.com/bangla-fonts.html> | Free to use and redistribute |
| Kalpurush | <https://www.omicronlab.com/bangla-fonts.html> | Free to use and redistribute |
| Amiri | <https://github.com/aliftype/amiri/releases> | SIL OFL 1.1 |
| Scheherazade New | <https://software.sil.org/scheherazade/> | SIL OFL 1.1 |

## Converting to woff2

The upstream downloads are `.ttf`. `woff2` is roughly a third of the size and
every browser this product supports reads it:

```bash
# Debian/Ubuntu: apt install woff2
woff2_compress SolaimanLipi.ttf      # → SolaimanLipi.woff2
```

Keep the filenames in the table above exactly — `src/index.css` names them, and
a renamed file fails silently as "the font just did not apply".
