/**
 * The fee receipt — the one piece of paper this system exists to produce.
 *
 * Adapted from Awliaa's `printInvoice.ts` (`CLAUDE.md` §3.1), with the shape a
 * Bangladeshi institution's receipt actually has: letterhead, the student and
 * their class, the invoice, the amount **in figures and in Bangla words**, how
 * it was paid, the receipt number, who took it and when.
 *
 * Printed by opening a window and writing a self-contained document into it
 * rather than by styling the app for `@media print`. The receipt has to survive
 * being printed from a screen the SPA is not on — the accountant collects the
 * next payment while the last one is still on the printer — and a print
 * stylesheet over the live DOM makes every layout change a chance to break the
 * paper.
 *
 * **Two paper sizes, chosen by the caller**: A4 for an office laser printer,
 * and 80mm for the thermal roll on a counter. Same document, one `@page` rule
 * and a width apart, because a counter has one printer and it is whichever one
 * the institution bought.
 */

import { formatBDTExact, toBanglaDigits } from './format';
import { takaInWordsBn, takaInWordsEn } from './money';
import { formatDhakaDate, formatDhakaDateTime } from './timezone';

export type ReceiptPaper = 'a4' | 'thermal';

export interface ReceiptData {
  /** The letterhead. Both names print — the Bangla large, the English under it. */
  institutionName: string;
  institutionNameBn: string;
  institutionAddress: string;
  institutionPhone: string;
  /** An absolute or API-relative URL. Omitted rather than broken if absent. */
  logoUrl?: string | null;

  receiptNo: string;
  paidAt: string;

  studentName: string;
  studentNameBn?: string;
  studentId?: string;
  admissionNo?: string;
  className?: string;

  invoiceNo: string;
  categoryName: string;
  period?: string;

  /** All four as the API's decimal strings. Nothing is computed here. */
  amount: string;
  invoicePayable: string;
  invoicePaid: string;
  invoiceBalance: string;

  methodLabel: string;
  transactionId?: string;
  collectedBy: string;
  note?: string;

  /** Printed across the page when the receipt has been reversed, so a reversed
   *  receipt cannot be handed over as a live one. */
  reversed?: boolean;
}

/** HTML-escape. Every value below is institution-entered text — a student named
 *  `<b>` must print as `<b>` and not as bold. */
function esc(value: string | null | undefined): string {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string,
  );
}

/** A money cell: figures in Bangla numerals, as a printed document is read. */
function money(value: string): string {
  return esc(toBanglaDigits(formatBDTExact(value)));
}

function row(labelBn: string, labelEn: string, value: string): string {
  if (!value) return '';
  return `<tr><th><span class="bn">${esc(labelBn)}</span><span class="en">${esc(labelEn)}</span></th><td>${value}</td></tr>`;
}

function receiptHtml(d: ReceiptData, paper: ReceiptPaper): string {
  const thermal = paper === 'thermal';

  return `<!doctype html>
<html lang="bn">
<head>
<meta charset="utf-8">
<title>${esc(d.receiptNo)}</title>
<style>
  @page { size: ${thermal ? '80mm auto' : 'A4'}; margin: ${thermal ? '4mm' : '14mm'}; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: 'Noto Sans Bengali', 'Nirmala UI', 'SolaimanLipi', system-ui, sans-serif;
    font-size: ${thermal ? '11px' : '13px'};
    color: #111;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .sheet { width: 100%; max-width: ${thermal ? '72mm' : '182mm'}; margin: 0 auto; }
  header { text-align: center; border-bottom: 2px solid #111; padding-bottom: 8px; }
  header img { max-height: ${thermal ? '36px' : '56px'}; margin-bottom: 6px; }
  .inst-bn { font-size: ${thermal ? '15px' : '21px'}; font-weight: 700; line-height: 1.25; }
  .inst-en { font-size: ${thermal ? '10px' : '13px'}; letter-spacing: .04em; text-transform: uppercase; }
  .inst-meta { font-size: ${thermal ? '9px' : '11px'}; color: #444; margin-top: 3px; }
  .title { margin: 10px 0 8px; text-align: center; font-weight: 700; font-size: ${thermal ? '12px' : '15px'};
           letter-spacing: .06em; }
  .meta { display: flex; justify-content: space-between; gap: 8px; font-size: ${thermal ? '9px' : '11px'};
          color: #333; margin-bottom: 8px; ${thermal ? 'flex-direction: column;' : ''} }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: ${thermal ? '3px 2px' : '5px 6px'}; vertical-align: top; text-align: left;
           border-bottom: 1px solid #e3e3e3; }
  th { width: ${thermal ? '46%' : '34%'}; font-weight: 600; color: #333; }
  th .en { display: block; font-size: ${thermal ? '8px' : '9px'}; color: #777; text-transform: uppercase;
           letter-spacing: .03em; font-weight: 400; }
  .paid { margin-top: 10px; border: 2px solid #111; padding: ${thermal ? '6px' : '10px'}; text-align: center; }
  .paid-label { font-size: ${thermal ? '9px' : '11px'}; letter-spacing: .06em; text-transform: uppercase; color: #333; }
  .paid-figure { font-size: ${thermal ? '18px' : '26px'}; font-weight: 700; line-height: 1.2; }
  .words { margin-top: 4px; font-size: ${thermal ? '9px' : '11px'}; font-style: italic; }
  .words-en { color: #555; font-size: ${thermal ? '8px' : '10px'}; }
  .balance { margin-top: 8px; display: flex; justify-content: space-between; font-weight: 600;
             font-size: ${thermal ? '10px' : '12px'}; }
  .balance.due { color: #b00020; }
  .auto { margin-top: 8px; font-size: ${thermal ? '8px' : '10px'}; color: #555; text-align: center; }
  .sign { margin-top: ${thermal ? '14px' : '34px'}; display: flex; justify-content: space-between; gap: 16px;
          font-size: ${thermal ? '9px' : '11px'}; }
  .sign div { flex: 1; border-top: 1px dotted #666; padding-top: 4px; text-align: center; }
  footer { margin-top: 10px; text-align: center; font-size: ${thermal ? '8px' : '9px'}; color: #777; }
  .void { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center;
          font-size: ${thermal ? '32px' : '80px'}; color: rgba(176,0,32,.18); font-weight: 800;
          transform: rotate(-24deg); pointer-events: none; }
</style>
</head>
<body>
${d.reversed ? '<div class="void">বাতিল / REVERSED</div>' : ''}
<div class="sheet">
  <header>
    ${d.logoUrl ? `<img src="${esc(d.logoUrl)}" alt="">` : ''}
    <div class="inst-bn">${esc(d.institutionNameBn || d.institutionName)}</div>
    <div class="inst-en">${esc(d.institutionName)}</div>
    <div class="inst-meta">${esc(d.institutionAddress)}${
      d.institutionPhone ? ` &middot; ${esc(d.institutionPhone)}` : ''
    }</div>
  </header>

  <div class="title">ফি আদায়ের রসিদ &middot; FEE RECEIPT</div>

  <div class="meta">
    <span><strong>রসিদ নং / Receipt:</strong> ${esc(d.receiptNo)}</span>
    <span><strong>তারিখ / Date:</strong> ${esc(
      formatDhakaDateTime(d.paidAt) === '—' ? formatDhakaDate(d.paidAt) : formatDhakaDateTime(d.paidAt),
    )}</span>
  </div>

  <table>
    ${row('শিক্ষার্থী', 'Student', esc(d.studentNameBn || d.studentName))}
    ${row('আইডি', 'Student ID', esc(d.studentId ?? ''))}
    ${row('ভর্তি নং', 'Admission no.', esc(d.admissionNo ?? ''))}
    ${row('শ্রেণি', 'Class', esc(d.className ?? ''))}
    ${row('বিল নং', 'Invoice', esc(d.invoiceNo))}
    ${row('ফি খাত', 'Fee head', esc(d.categoryName))}
    ${row('মাস', 'Period', esc(d.period ?? ''))}
    ${row('পরিশোধের মাধ্যম', 'Method', esc(d.methodLabel))}
    ${row('লেনদেন আইডি', 'Transaction id', esc(d.transactionId ?? ''))}
    ${row('মন্তব্য', 'Note', esc(d.note ?? ''))}
  </table>

  <div class="paid">
    <div class="paid-label">এই রসিদে গৃহীত / Received now</div>
    <div class="paid-figure">${money(d.amount)}</div>
    <div class="words">${esc(takaInWordsBn(d.amount))}</div>
    <div class="words words-en">${esc(takaInWordsEn(d.amount))}</div>
  </div>

  <div class="balance">
    <span>বিলের মোট / Invoice total</span><span>${money(d.invoicePayable)}</span>
  </div>
  <div class="balance">
    <span>মোট পরিশোধিত / Paid to date</span><span>${money(d.invoicePaid)}</span>
  </div>
  <div class="balance${d.invoiceBalance && d.invoiceBalance !== '0.00' ? ' due' : ''}">
    <span>অবশিষ্ট বকেয়া / Balance remaining</span><span>${money(d.invoiceBalance)}</span>
  </div>

  <div class="auto">
    এই আদায় স্বয়ংক্রিয়ভাবে আয় খাতে যুক্ত হয়েছে &middot;
    This collection has already been posted to income.
  </div>

  <div class="sign">
    <div>আদায়কারী / Received by<br><strong>${esc(d.collectedBy)}</strong></div>
    <div>অভিভাবকের স্বাক্ষর / Guardian</div>
  </div>

  <footer>SIES &middot; কম্পিউটারে তৈরি রসিদ / Computer-generated receipt</footer>
</div>
</body>
</html>`;
}

/**
 * Open the receipt in a print window.
 *
 * Returns `false` when the browser blocked the pop-up, so the caller can say so
 * instead of leaving the clerk waiting for paper that is never coming. The
 * window is left open after printing rather than closed: a thermal printer that
 * jams is a receipt the clerk needs to be able to send again.
 */
export function printReceipt(data: ReceiptData, paper: ReceiptPaper = 'a4'): boolean {
  const win = window.open('', '_blank', 'width=820,height=900');
  if (!win) return false;

  win.document.open();
  win.document.write(receiptHtml(data, paper));
  win.document.close();

  // The logo is a network image; printing before it decodes prints a gap where
  // the letterhead should be. `onload` fires after the images have settled.
  win.onload = () => {
    win.focus();
    win.print();
  };
  // A document with no external image never fires onload after `document.close`
  // in every browser, so nudge it once on the next frame as well. Printing
  // twice is not possible — the second call runs only if the first never did.
  let printed = false;
  const nudge = () => {
    if (printed) return;
    printed = true;
    win.focus();
    win.print();
  };
  win.onload = () => nudge();
  setTimeout(nudge, 700);

  return true;
}
