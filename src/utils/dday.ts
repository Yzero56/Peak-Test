/** 자정 기준으로 두 날짜의 일수 차이를 계산합니다. */
function daysBetween(from: Date, to: Date): number {
  const a = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  const b = new Date(to.getFullYear(), to.getMonth(), to.getDate());
  return Math.round((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24));
}

export function getDday(expiresAt: string, today: Date = new Date()): number {
  return daysBetween(today, new Date(expiresAt));
}

export function formatDday(dday: number): string {
  if (dday === 0) return 'D-Day';
  return dday > 0 ? `D-${dday}` : `D+${Math.abs(dday)}`;
}

export type FreshnessStatus = 'expired' | 'urgent' | 'caution' | 'fresh';

export function getFreshnessStatus(dday: number): FreshnessStatus {
  if (dday <= 0) return 'expired';
  if (dday <= 2) return 'urgent';
  if (dday <= 5) return 'caution';
  return 'fresh';
}

export const freshnessStyles: Record<
  FreshnessStatus,
  { badge: string; badgeText: string; dot: string; label: string }
> = {
  expired: {
    badge: 'bg-red-100 dark:bg-red-950',
    badgeText: 'text-red-600 dark:text-red-400',
    dot: 'bg-red-500',
    label: '유통기한 지남',
  },
  urgent: {
    badge: 'bg-orange-100 dark:bg-orange-950',
    badgeText: 'text-orange-600 dark:text-orange-400',
    dot: 'bg-orange-500',
    label: '임박',
  },
  caution: {
    badge: 'bg-amber-100 dark:bg-amber-950',
    badgeText: 'text-amber-700 dark:text-amber-400',
    dot: 'bg-amber-500',
    label: '주의',
  },
  fresh: {
    badge: 'bg-emerald-100 dark:bg-emerald-950',
    badgeText: 'text-emerald-700 dark:text-emerald-400',
    dot: 'bg-emerald-500',
    label: '신선',
  },
};
