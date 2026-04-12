export function relativeTimeFromIso(isoTimestamp: string, now: Date = new Date()): string {
  const eventTime = new Date(isoTimestamp);
  if (Number.isNaN(eventTime.getTime())) {
    return isoTimestamp.slice(0, 10);
  }

  const diffMs = now.getTime() - eventTime.getTime();
  if (diffMs < 0) {
    return isoTimestamp.slice(0, 10);
  }

  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 60) {
    return `${Math.max(1, minutes)} mins ago`;
  }

  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} hrs ago`;
  }

  const days = Math.floor(hours / 24);
  if (days < 7) {
    return `${days} days ago`;
  }

  return isoTimestamp.slice(0, 10);
}
