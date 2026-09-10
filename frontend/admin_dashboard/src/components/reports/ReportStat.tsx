/**
 * One figure at the top of a report.
 *
 * Not `StatCard`: that card is the dashboard's, and it leads with a tinted
 * icon square because it is competing for attention on a landing screen. A
 * report is already the thing the reader chose to open, so its totals are a
 * label and a number, and a row of six of them stays readable at 360px.
 */
export default function ReportStat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <p className="text-xs uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-1 text-xl font-bold tabular-nums text-gray-900">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-500">{sub}</p>}
    </div>
  );
}
