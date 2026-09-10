/**
 * Preparing a server-rendered form for the screen and the printer.
 *
 * **Nothing here decides how a block looks.** `forms/renderer.py` renders the
 * document (`docs/07` §8) and this file only does the two things a browser
 * cannot be told from Python:
 *
 *  1. **It attaches the self-hosted faces.** The renderer's CSS names a Bangla
 *     and an Arabic stack but cannot know where this deployment keeps the
 *     files. The faces below are the ones committed in `public/fonts/`, which
 *     is what makes a form print correctly on an office machine with no
 *     internet (§8) — the whole reason they are self-hosted at all.
 *  2. **It joins several documents into one print job.** Selecting six
 *     applicants on the admissions list has to be one trip to the printer, not
 *     six dialogs.
 *
 * The join is textual and structural — each document's own `<style>` and its
 * own body, in order, separated by a page break. It re-lays out nothing.
 */

// The three ranges Google subsets these faces by, copied from the @font-face
// block in `index.css` so the file names and the ranges stay one decision. A
// page of Latin text never pulls the Bengali block.
const BENGALI =
  'U+0951-0952, U+0964-0965, U+0980-09FE, U+1CD0, U+1CD2, U+1CD5-1CD6, U+1CD8, ' +
  'U+1CE1, U+1CEA, U+1CED, U+1CF2, U+1CF5-1CF7, U+200C-200D, U+20B9, U+25CC, U+A8F1';

const ARABIC =
  'U+0600-06FF, U+0750-077F, U+0870-088E, U+0890-0891, U+0897-08E1, U+08E3-08FF, ' +
  'U+200C-200E, U+2010-2011, U+204F, U+2E41, U+FB50-FDFF, U+FE70-FE74, U+FE76-FEFC, ' +
  'U+102E0-102FB, U+10E60-10E7E, U+1EE00-1EE03, U+1EE05-1EE1F, U+1EE21-1EE22, U+1EE24, ' +
  'U+1EE27, U+1EE29-1EE32, U+1EE34-1EE37, U+1EE39, U+1EE3B, U+1EE42, U+1EE47, U+1EE49, ' +
  'U+1EE4B, U+1EE4D-1EE4F, U+1EE51-1EE52, U+1EE54, U+1EE57, U+1EE59, U+1EE5B, U+1EE5D, ' +
  'U+1EE5F, U+1EE61-1EE62, U+1EE64, U+1EE67-1EE6A, U+1EE6C-1EE72, U+1EE74-1EE77, ' +
  'U+1EE79-1EE7C, U+1EE7E, U+1EE80-1EE89, U+1EE8B-1EE9B, U+1EEA1-1EEA3, U+1EEA5-1EEA9, ' +
  'U+1EEAB-1EEBB, U+1EEF0-1EEF1';

const LATIN_EXT =
  'U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, ' +
  'U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, ' +
  'U+2113, U+2C60-2C7F, U+A720-A7FF';

const LATIN =
  'U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, ' +
  'U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, ' +
  'U+FEFF, U+FFFD';

/** The SPA's basename. The fonts are served from the same origin as this page,
 *  so an absolute path works in the frame without a `<base>` tag. */
const FONT_DIR = '/myadmin/fonts';

function face(family: string, file: string, weight: number, range: string): string {
  return `@font-face{font-family:'${family}';font-style:normal;font-weight:${weight};` +
    `font-display:block;src:url('${FONT_DIR}/${file}') format('woff2');` +
    `unicode-range:${range};}`;
}

/**
 * `font-display: block` and not `swap`, deliberately — this is the one place in
 * the product where it is right. A print dialog opened while a face is still
 * swapping captures the fallback, and a form whose Bangla came out in Nirmala
 * UI is the kind of defect nobody notices until it is on paper.
 */
const FONT_CSS = [
  ...[400, 500, 600, 700].flatMap((weight) => [
    face('Hind Siliguri', `HindSiliguri-${weight}-0.woff2`, weight, BENGALI),
    face('Hind Siliguri', `HindSiliguri-${weight}-1.woff2`, weight, LATIN_EXT),
    face('Hind Siliguri', `HindSiliguri-${weight}-2.woff2`, weight, LATIN),
  ]),
  ...[400, 700].flatMap((weight) => [
    face('Amiri', `Amiri-${weight}-0.woff2`, weight, ARABIC),
    face('Amiri', `Amiri-${weight}-1.woff2`, weight, LATIN_EXT),
    face('Amiri', `Amiri-${weight}-2.woff2`, weight, LATIN),
  ]),
  // Put the shipped faces at the FRONT of the renderer's own stacks rather than
  // replacing them: an office machine that really does have SolaimanLipi
  // installed should still be free to use it if these ever fail to load.
  `body{font-family:'Hind Siliguri','SolaimanLipi','Kalpurush','Nirmala UI',sans-serif;}`,
  `.ar{font-family:'Amiri','Scheherazade New','Traditional Arabic',serif;}`,
].join('\n');

/** Screen-only chrome for the preview frame. Inside `@media screen` so not one
 *  pixel of it can reach the paper. */
const PREVIEW_CSS = `
@media screen {
  body { background: #e5e7eb; padding: 6mm 0; }
  .sheet {
    background: #fff;
    padding: 12mm 14mm;
    box-shadow: 0 1px 3px rgba(0,0,0,.2);
    margin-bottom: 6mm;
  }
}
`;

/** The `<style>` blocks and the body of one rendered document. */
function parts(html: string): { style: string; body: string } {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const style = Array.from(doc.querySelectorAll('style'))
    .map((node) => node.textContent ?? '')
    .join('\n');
  return { style, body: doc.body.innerHTML };
}

/**
 * Several rendered documents as one printable page.
 *
 * Every document these come from is the same template rendered by the same
 * server, so the first one's stylesheet governs the lot; the rest are collected
 * anyway and de-duplicated, because a batch that ever mixes two templates must
 * not silently print the second one with the first one's CSS.
 */
export function mergePrintDocuments(documents: string[]): string {
  const styles: string[] = [];
  const bodies: string[] = [];

  documents.forEach((html) => {
    const { style, body } = parts(html);
    if (style && !styles.includes(style)) styles.push(style);
    bodies.push(body);
  });

  return (
    '<!DOCTYPE html><html lang="bn"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    `<style>${styles.join('\n')}</style>` +
    `<style>${FONT_CSS}</style>` +
    `<style>${PREVIEW_CSS}</style>` +
    '</head><body>' +
    // Each document after the first starts on a fresh sheet. The class is the
    // renderer's own, so the rule that implements it is already in the CSS
    // above rather than invented here.
    bodies.join('<div class="page-break"></div>') +
    '</body></html>'
  );
}
