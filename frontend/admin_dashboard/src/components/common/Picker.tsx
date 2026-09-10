import { selectCls } from './styles';

/**
 * A `<select>` that stops being a `<select>` when there is nothing to choose.
 *
 * `CLAUDE.md` §7b rule 3: **if there is exactly one option, do not render a
 * picker at all.** Most institutions run one session and give most classes one
 * section, so a dropdown holding a single entry is not a rare edge — it is what
 * half the pickers in this app look like on a real install, and every one of
 * them is a control that cannot do anything.
 *
 * Centralised rather than written out at each of the dozen call sites so that
 * the collapsed form looks the same everywhere — a label that shifts the row's
 * height when a second section is added is worse than the dropdown was.
 *
 * Nothing is reported upward when it collapses, and nothing needs to be: every
 * caller derives its value as `explicitChoice || obviousDefault || first`
 * (§7b), so with one option the value already *is* that option before this
 * component is reached.
 */

export interface PickerOption {
  value: string;
  label: string;
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  options: PickerOption[];
  /**
   * The leading "" entry — `"Every status"`, `"Whole class"`. Its presence
   * means the picker has **two** answers even with one option, so it is never
   * collapsed to text.
   */
  anyLabel?: string;
  /** Shown in place of the list when there is nothing at all to offer. */
  emptyLabel?: string;
  className?: string;
  'aria-label'?: string;
  disabled?: boolean;
}

export default function Picker({
  value,
  onChange,
  options,
  anyLabel,
  emptyLabel,
  className = selectCls,
  disabled = false,
  ...rest
}: Props) {
  const only = anyLabel === undefined && options.length === 1 ? options[0] : null;

  if (only) {
    return (
      <span
        className="flex min-h-[44px] items-center px-1 text-base font-medium text-gray-900"
        {...rest}
      >
        {only.label}
      </span>
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={className}
      disabled={disabled}
      {...rest}
    >
      {anyLabel !== undefined && <option value="">{anyLabel}</option>}
      {options.length === 0 && emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
