/** Human-readable interval: "<1 min", "10 min", "3 h", "4 d", "2 mo", "1.3 y". */
export function formatInterval(seconds: number): string {
  const minute = 60;
  const hour = 3600;
  const day = 86400;
  if (seconds < minute) return "<1 min";
  if (seconds < hour) return `${Math.round(seconds / minute)} min`;
  if (seconds < day) return `${Math.round(seconds / hour)} h`;
  if (seconds < 30 * day) return `${Math.round(seconds / day)} d`;
  if (seconds < 365 * day) return `${Math.round(seconds / (30 * day))} mo`;
  const years = Math.round((seconds / (365 * day)) * 10) / 10;
  return `${years} y`;
}
