import { useCallback, useEffect, useRef, useState } from 'react';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import { mergePrintDocuments } from './printDocument';

/**
 * The printed form, on screen and then on paper (`docs/07` §8, §9).
 *
 * **The document is rendered by the server and shown in an `<iframe>`.** Two
 * reasons, and both are load-bearing:
 *
 *  - The form's print CSS sets `@page`, page breaks and a 12pt body. Dropped
 *    into the dashboard's DOM it would fight Tailwind's reset in both
 *    directions, and `window.print()` on the dashboard would print the sidebar.
 *    A frame is a clean document boundary, so `iframe.contentWindow.print()`
 *    prints the FORM and nothing else.
 *  - The HTML needs the JWT to fetch, and `<iframe src>` cannot send an
 *    Authorization header — so the document is fetched by `apiClient` and
 *    written into the frame through `srcdoc`, which keeps it same-origin and
 *    therefore printable and measurable from here.
 *
 * **On a phone the A4 page does not reflow** — that is `CLAUDE.md` §7a's one
 * stated exception. The sheet keeps its width and the PREVIEW is what adapts:
 * a pinch-zoomable, horizontally scrolling container, a zoom control for
 * anybody whose fingers are full of paperwork, and a full-width Print button.
 */

/**
 * What to preview. A new `key` is what triggers a fetch, so a re-render never
 * re-requests: on the filled path the request is not idempotent — it issues a
 * form number and records a `PrintedForm` (`docs/07` §6).
 */
export interface PreviewRequest {
  key: string;
  title: string;
  /** One line under the title saying what this document IS — a blank stack, a
   *  reprint from a snapshot, six forms in one job. */
  note?: string;
  /** The documents, in print order. One entry per sheet-set. */
  load: () => Promise<string[]>;
}

/** A4 is 210mm wide. The frame is that, always, at every screen size. */
const SHEET_WIDTH_MM = 210;

export default function FormPreviewModal({
  request,
  onClose,
}: {
  request: PreviewRequest | null;
  onClose: () => void;
}) {
  const { t } = useT();

  const [html, setHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [frameHeight, setFrameHeight] = useState(1123); // A4 at 96dpi, until measured

  const frameRef = useRef<HTMLIFrameElement>(null);
  // The key already fetched. Without it a parent re-render would re-run the
  // effect and print a second form number for a preview nobody asked for twice.
  const fetchedKey = useRef<string | null>(null);

  useEffect(() => {
    if (!request) {
      fetchedKey.current = null;
      return;
    }
    if (fetchedKey.current === request.key) return;
    fetchedKey.current = request.key;

    let alive = true;
    setHtml(null);
    setError(null);
    setLoading(true);
    // The zoom that fits a phone. Recomputed per document rather than kept,
    // because the last thing someone zoomed into is not where the next form
    // should open.
    setZoom(window.innerWidth < 640 ? 0.42 : 1);

    void request
      .load()
      .then((documents) => {
        if (!alive) return;
        setHtml(mergePrintDocuments(documents));
      })
      .catch((err: unknown) => {
        if (alive) setError(apiErrorText(err, t, t('Could not produce this form.')));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [request, t]);

  /** The frame is same-origin, so its own content height is readable — which is
   *  what lets a two-page form scroll in the modal instead of inside a nested
   *  scrollbar nobody can reach with a thumb. */
  const measure = useCallback(() => {
    const doc = frameRef.current?.contentDocument;
    if (doc?.body) setFrameHeight(Math.max(doc.body.scrollHeight + 24, 400));
  }, []);

  const print = () => {
    const frame = frameRef.current?.contentWindow;
    if (!frame) return;
    frame.focus();
    frame.print();
  };

  const open = request !== null;

  return (
    <BaseModal
      isOpen={open}
      onClose={onClose}
      title={request?.title ?? ''}
      maxWidth="6xl"
      footer={
        <div className="flex flex-col gap-2 sm:flex-row-reverse">
          <button
            type="button"
            onClick={print}
            disabled={!html}
            className="tap w-full justify-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 sm:w-auto"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2M6 14h12v8H6v-8z"
              />
            </svg>
            {t('Print')}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="tap w-full justify-center rounded-lg border border-gray-200 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50 sm:w-auto"
          >
            {t('Close')}
          </button>
        </div>
      }
    >
      <div className="space-y-3">
        {request?.note && (
          <p className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs leading-relaxed text-blue-900">
            {request.note}
          </p>
        )}

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {loading && (
          <p className="py-10 text-center text-sm text-gray-500">{t('Preparing the form…')}</p>
        )}

        {html && (
          <>
            {/* Zoom, for the phone. Buttons as well as pinch, because the
                container is the only pinch surface and a one-handed user at a
                counter has no second hand to pinch with. */}
            <div className="flex items-center justify-between gap-2 sm:justify-end">
              <span className="text-xs text-gray-500">{t('A4 · 210 × 297 mm')}</span>
              <div className="inline-flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setZoom((z) => Math.max(0.25, Math.round((z - 0.15) * 100) / 100))}
                  className="tap h-11 w-11 justify-center rounded-lg border border-gray-200 text-lg font-medium text-gray-700"
                  aria-label={t('Zoom out')}
                >
                  −
                </button>
                <span className="w-14 text-center text-xs tabular-nums text-gray-600">
                  {Math.round(zoom * 100)}%
                </span>
                <button
                  type="button"
                  onClick={() => setZoom((z) => Math.min(2, Math.round((z + 0.15) * 100) / 100))}
                  className="tap h-11 w-11 justify-center rounded-lg border border-gray-200 text-lg font-medium text-gray-700"
                  aria-label={t('Zoom in')}
                >
                  +
                </button>
              </div>
            </div>

            {/* The one container allowed to scroll sideways (§7a rule 1).
                `touch-action: pinch-zoom` lets the browser's own pinch work on
                it; the transform below is what the buttons drive. */}
            <div
              className="overflow-auto rounded-lg border border-gray-200 bg-gray-100"
              style={{ touchAction: 'pinch-zoom', WebkitOverflowScrolling: 'touch' }}
            >
              {/* Two boxes, and both are needed. The outer one carries the
                  SCALED footprint so the scroll area matches what is drawn — a
                  transform alone leaves the parent reserving the unscaled size,
                  and the preview then scrolls past the end of the page. */}
              <div
                style={{
                  width: `calc(${SHEET_WIDTH_MM}mm * ${zoom})`,
                  height: frameHeight * zoom,
                }}
              >
                <div
                  style={{
                    width: `${SHEET_WIDTH_MM}mm`,
                    height: frameHeight,
                    transform: `scale(${zoom})`,
                    transformOrigin: 'top left',
                  }}
                >
                  <iframe
                    ref={frameRef}
                    title={request?.title ?? t('Form preview')}
                    srcDoc={html}
                    onLoad={measure}
                    // Never sandboxed away from its origin: the frame MUST stay
                    // same-origin, or `contentWindow.print()` is a cross-origin
                    // call and the Print button silently does nothing.
                    className="block border-0 bg-white"
                    style={{ width: `${SHEET_WIDTH_MM}mm`, height: frameHeight }}
                  />
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </BaseModal>
  );
}
