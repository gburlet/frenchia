import { useState } from "react";
import type { DayActivity } from "@/lib/api/progress";
import { cn } from "@/lib/utils";

const dayLabel = new Intl.DateTimeFormat("en-CA", { weekday: "short", day: "numeric", month: "short" });
const weekday = new Intl.DateTimeFormat("en-CA", { weekday: "narrow" });

/** "2026-10-25" as a local date (not UTC midnight, which is the previous day here). */
function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y!, m! - 1, d!);
}

function describe(day: DayActivity): string {
  const kinds = Object.entries(day.by_kind)
    .map(([kind, n]) => `${n} ${kind}`)
    .join(", ");
  const base = `${dayLabel.format(parseDay(day.date))}: ${day.items} item${day.items === 1 ? "" : "s"}`;
  return day.items ? `${base}, ${day.minutes} min${kinds ? ` (${kinds})` : ""}` : `${base}`;
}

/** Items practised per day: one series, columns from a shared baseline, hover/focus tooltips. */
export function ActivityChart({ days }: { days: DayActivity[] }) {
  const [active, setActive] = useState<number | null>(null);
  const max = Math.max(1, ...days.map((d) => d.items));
  const last = days.length - 1;
  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="sr-only">Items practised per day, last {days.length} days</figcaption>
      <div className="relative">
        <ol className="flex h-28 items-end gap-0.5 border-b border-line" onMouseLeave={() => setActive(null)}>
          {days.map((day, i) => {
            const height = day.items ? Math.max(4, Math.round((day.items / max) * 100)) : 0;
            return (
              <li
                key={day.date}
                tabIndex={0}
                aria-label={describe(day)}
                onMouseEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                className="group relative flex h-full flex-1 cursor-default items-end justify-center rounded-t focus-visible:outline-2 focus-visible:outline-purple"
              >
                <span
                  aria-hidden
                  className={cn(
                    "block w-full max-w-6 rounded-t-[4px] bg-teal transition-opacity",
                    active !== null && active !== i && "opacity-50",
                  )}
                  style={{ height: `${height}%` }}
                />
                {i === last && day.items > 0 && (
                  <span aria-hidden className="absolute -top-5 text-xs font-bold text-heading">
                    {day.items}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
        {active !== null && (
          <div
            role="tooltip"
            className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-control bg-log px-2 py-1 text-xs text-heading shadow-card"
            style={{ left: `${((active + 0.5) / days.length) * 100}%` }}
          >
            {describe(days[active]!)}
          </div>
        )}
      </div>
      <ol aria-hidden className="flex gap-0.5 text-center text-xs text-muted">
        {days.map((day, i) => (
          <li key={day.date} className={cn("flex-1", i === last && "font-bold text-detail")}>
            {weekday.format(parseDay(day.date))}
          </li>
        ))}
      </ol>
      <details className="text-sm text-detail">
        <summary className="cursor-pointer text-muted hover:text-detail">Show as table</summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr className="text-muted">
              <th scope="col" className="font-normal">Day</th>
              <th scope="col" className="font-normal">Items</th>
              <th scope="col" className="font-normal">Minutes</th>
            </tr>
          </thead>
          <tbody>
            {days.map((day) => (
              <tr key={day.date}>
                <td>{dayLabel.format(parseDay(day.date))}</td>
                <td>{day.items}</td>
                <td>{day.minutes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

/** A 0-1 score as a labelled horizontal bar (value at the tip, in text colour). */
export function Meter({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-3">
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-valuetext={`${pct}%`}
        className="h-2 flex-1 rounded-full bg-chrome"
      >
        <div className="h-full rounded-full bg-teal" style={{ width: `${Math.max(pct, 2)}%` }} />
      </div>
      <span className="w-10 text-right text-sm tabular-nums text-detail">{pct}%</span>
    </div>
  );
}
