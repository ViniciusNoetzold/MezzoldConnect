import { DateTime } from 'luxon';

export interface QuietHoursWindow {
  timezone: string;
  start: string;
  end: string;
}

const parseClockMinutes = (value: string): number => {
  const [hour = '0', minute = '0'] = value.split(':');
  return Number.parseInt(hour, 10) * 60 + Number.parseInt(minute, 10);
};

const applyClock = (date: DateTime, clock: string): DateTime => {
  const [hour = '0', minute = '0', second = '0'] = clock.split(':');
  return date.set({
    hour: Number.parseInt(hour, 10),
    minute: Number.parseInt(minute, 10),
    second: Number.parseInt(second, 10),
    millisecond: 0
  });
};

export function isWithinQuietHours(candidate: Date, window: QuietHoursWindow): boolean {
  const local = DateTime.fromJSDate(candidate, { zone: window.timezone });
  const currentMinutes = local.hour * 60 + local.minute;
  const startMinutes = parseClockMinutes(window.start);
  const endMinutes = parseClockMinutes(window.end);

  if (startMinutes === endMinutes) return false;
  if (startMinutes < endMinutes) {
    return currentMinutes >= startMinutes && currentMinutes < endMinutes;
  }

  return currentMinutes >= startMinutes || currentMinutes < endMinutes;
}

export function nextAllowedSendTime(candidate: Date, window: QuietHoursWindow): Date {
  if (!isWithinQuietHours(candidate, window)) return candidate;

  const local = DateTime.fromJSDate(candidate, { zone: window.timezone });
  const currentMinutes = local.hour * 60 + local.minute;
  const startMinutes = parseClockMinutes(window.start);
  const endMinutes = parseClockMinutes(window.end);

  if (startMinutes < endMinutes) {
    return applyClock(local, window.end).toJSDate();
  }

  const endToday = applyClock(local, window.end);
  const endIsTomorrow = currentMinutes >= startMinutes;
  return (endIsTomorrow ? endToday.plus({ days: 1 }) : endToday).toJSDate();
}

export function millisecondsUntilAllowed(candidate: Date, window: QuietHoursWindow): number {
  return Math.max(0, nextAllowedSendTime(candidate, window).getTime() - candidate.getTime());
}

export function nextQuotaWindowStart(now: Date, window: QuietHoursWindow): Date {
  const local = DateTime.fromJSDate(now, { zone: window.timezone }).plus({ days: 1 }).startOf('day');
  return nextAllowedSendTime(applyClock(local, window.end).toJSDate(), window);
}
