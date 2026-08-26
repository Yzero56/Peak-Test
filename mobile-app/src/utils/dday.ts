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
