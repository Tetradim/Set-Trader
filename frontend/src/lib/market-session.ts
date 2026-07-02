export type UsEquitySessionStatus = 'pre' | 'open' | 'after' | 'closed';

export type UsEquitySession = {
  label: string;
  status: UsEquitySessionStatus;
};

const SESSION_LABELS: Record<UsEquitySessionStatus, string> = {
  pre: 'Pre-Market',
  open: 'Market Open',
  after: 'After-Hours',
  closed: 'Closed',
};

const WEEKDAY_INDEX: Record<string, number> = {
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
  Sun: 7,
};

const ET_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  hourCycle: 'h23',
});

function getEasternParts(now: Date): { weekday: number; minutes: number } {
  const parts = ET_FORMATTER.formatToParts(now);
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  const hour = Number(value('hour'));
  const minute = Number(value('minute'));

  return {
    weekday: WEEKDAY_INDEX[value('weekday')] ?? 0,
    minutes: hour * 60 + minute,
  };
}

export function getUsEquitySession(now = new Date()): UsEquitySession {
  const { weekday, minutes } = getEasternParts(now);
  let status: UsEquitySessionStatus = 'closed';

  if (weekday >= 1 && weekday <= 5) {
    if (minutes >= 4 * 60 && minutes < 9 * 60 + 30) {
      status = 'pre';
    } else if (minutes >= 9 * 60 + 30 && minutes < 16 * 60) {
      status = 'open';
    } else if (minutes >= 16 * 60 && minutes < 20 * 60) {
      status = 'after';
    }
  }

  return { label: SESSION_LABELS[status], status };
}
