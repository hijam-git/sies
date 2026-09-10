/**
 * A status, drawn as a coloured dot and one word.
 *
 * It replaces the pill badge the list screens used to carry. A pill is a
 * heading-sized object repeated down every row for a value that is "active" on
 * nine rows in ten, and its padding was part of what made a row 69px tall. The
 * dot carries the same signal at a glance and costs the row nothing.
 *
 * **One word, in one language.** The old badge read `Active · অধ্যয়নরত` —
 * the same fact twice, because the API's `*_display` string concatenates both.
 * The app already knows which language the user reads (`lib/i18n`); the caller
 * passes the translated word and the badge says it once.
 */
export default function StatusDot({
  tone,
  label,
}: {
  tone: 'green' | 'amber' | 'red' | 'gray' | 'blue';
  /** Already translated, and one word where the language allows it. */
  label: string;
}) {
  const ink = {
    green: 'bg-emerald-500',
    amber: 'bg-amber-500',
    red: 'bg-red-500',
    gray: 'bg-gray-300',
    blue: 'bg-blue-500',
  }[tone];

  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${ink}`} aria-hidden />
      <span className="text-gray-700">{label}</span>
    </span>
  );
}
