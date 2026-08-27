import type {
  Category,
  InventoryItem,
  MealLogEntry,
  MealSlot,
  RecipeDef,
} from '@/types/fridge';
import { getDday } from '@/utils/dday';

export type PillTone = {
  containerClass: string;
  textClass: string;
};

/** 위험도는 앰버 한 축으로만 표시: 오늘/지남은 진하게, 내일은 연하게, 그 외는 중립. */
export function pillTone(dday: number): PillTone {
  if (dday <= 0) return { containerClass: 'bg-amber-300', textClass: 'font-bold text-amber-950' };
  if (dday === 1) return { containerClass: 'bg-amber-100', textClass: 'font-semibold text-amber-700' };
  if (dday <= 4) return { containerClass: 'bg-neutral-200', textClass: 'font-medium text-neutral-800' };
  return { containerClass: 'bg-neutral-200', textClass: 'text-neutral-700' };
}

export function ddayLabel(dday: number): string {
  if (dday < 0) return `D+${-dday}`;
  if (dday === 0) return '오늘';
  return `D-${dday}`;
}

export type ChipTone = { containerClass: string; textClass: string };

export function chipTone(active: boolean): ChipTone {
  return active
    ? { containerClass: 'bg-accent-700', textClass: 'font-semibold text-white' }
    : { containerClass: 'bg-neutral-200', textClass: 'text-neutral-700' };
}

const NAME_ICONS: Record<string, string> = {
  대파: '🌿', 우유: '🥛', 애호박: '🥒', 닭가슴살: '🍗', 식빵: '🍞', 시금치: '🥬',
  연어: '🐟', 플레인요거트: '🥣', 요거트: '🥣', 파프리카: '🫑', 두부: '🧈', 계란: '🥚',
  당근: '🥕', 양파: '🧅', 버터: '🧈', 방울토마토: '🍅', 토마토: '🍅', 감자: '🥔',
  마늘: '🧄', 김치: '🥬', 삼겹살: '🥓', '모짜렐라 치즈': '🧀',
};

const CATEGORY_ICONS: Record<Category, { emoji: string; bgClass: string }> = {
  채소: { emoji: '🥬', bgClass: 'bg-[#ebf7f1]' },
  '육류·계란': { emoji: '🍖', bgClass: 'bg-[#fdeeeb]' },
  유제품: { emoji: '🥛', bgClass: 'bg-[#eef2f8]' },
  수산물: { emoji: '🐟', bgClass: 'bg-[#e9f4f8]' },
  기타: { emoji: '🧺', bgClass: 'bg-neutral-200' },
};

export function iconFor(name: string, category: Category | ''): { emoji: string; bgClass: string } {
  const fallback = category ? CATEGORY_ICONS[category] : { emoji: '🧺', bgClass: 'bg-neutral-200' };
  return { emoji: NAME_ICONS[name] ?? fallback.emoji, bgClass: fallback.bgClass };
}

export type DecoratedItem = InventoryItem & {
  dday: number;
  ddayLabel: string;
  pill: PillTone;
  emoji: string;
  iconBgClass: string;
  sub: string;
};

export function decorateItem(item: InventoryItem, today: Date = new Date()): DecoratedItem {
  const dday = getDday(item.expiresAt, today);
  const icon = iconFor(item.name, item.category);
  return {
    ...item,
    dday,
    ddayLabel: ddayLabel(dday),
    pill: pillTone(dday),
    emoji: icon.emoji,
    iconBgClass: icon.bgClass,
    sub: `${item.quantity} · ${item.location}`,
  };
}

export const CATEGORY_ORDER: Category[] = ['채소', '육류·계란', '유제품', '수산물', '기타'];

export function groupByCategory(items: DecoratedItem[]): { category: Category; items: DecoratedItem[] }[] {
  return CATEGORY_ORDER
    .map((category) => ({ category, items: items.filter((i) => i.category === category) }))
    .filter((g) => g.items.length > 0);
}

export type RecipeMatch = {
  recipe: RecipeDef;
  pct: number;
  hits: number;
  have: string[];
  missing: string[];
  isGoodMatch: boolean;
};

// 레시피 API(식품안전나라)가 주는 재료명이 냉장고 재고에 적어둔 이름과 살짝 다른 경우가
// 흔하다(예: "달걀" vs "계란", "다진마늘" vs "마늘"). 동의어/수식어 차이를 흡수해 같은
// 재료로 인식시킨다.
const INGREDIENT_SYNONYMS: Record<string, string> = {
  달걀: '계란',
  메추리알: '계란',
  대파: '파',
  쪽파: '파',
  실파: '파',
  다진마늘: '마늘',
  다진양파: '양파',
  다진생강: '생강',
  홍고추: '고추',
  청양고추: '고추',
};

function canonicalIngredientName(name: string): string {
  if (INGREDIENT_SYNONYMS[name]) return INGREDIENT_SYNONYMS[name];
  for (const [alias, canon] of Object.entries(INGREDIENT_SYNONYMS)) {
    if (name.includes(alias)) return canon;
  }
  return name;
}

/** 재료명이 정확히 같지 않아도(동의어·수식어 차이) 같은 재료면 매칭시킨다.
 *
 * 단순 부분 문자열 포함 검사는 쓰지 않는다 — "파"가 "파프리카"에 포함된다는 이유로
 * 오매칭되는 등 짧은 재료명에서 오탐이 잦았다. 대신 위에 정리해둔 동의어 표로만 판단한다.
 */
export function ingredientMatches(ingredientName: string, itemName: string): boolean {
  if (ingredientName === itemName) return true;
  return canonicalIngredientName(ingredientName) === canonicalIngredientName(itemName);
}

function findMatchingName(ingredientName: string, names: string[]): string | undefined {
  return names.find((n) => ingredientMatches(ingredientName, n));
}

export function matchRecipe(recipe: RecipeDef, decorated: DecoratedItem[]): RecipeMatch {
  const names = decorated.map((i) => i.name);
  const have = recipe.uses.filter((u) => findMatchingName(u.name, names) != null).map((u) => u.name);
  const missing = recipe.uses.filter((u) => findMatchingName(u.name, names) == null).map((u) => u.name);
  const pct = Math.round((have.length / recipe.uses.length) * 100);
  const hits = recipe.uses.filter((u) => {
    const matchedName = findMatchingName(u.name, names);
    const item = matchedName != null ? decorated.find((i) => i.name === matchedName) : undefined;
    return item != null && item.dday <= 2;
  }).length;
  // 목업 레시피(재료 3~4개)에 맞춰 잡혀있던 75%는 API 레시피(평균 재료 9~10개)엔 너무
  // 빡빡해서(재료 1개 차이로도 못 넘김) 40%로 낮췄다.
  return { recipe, pct, hits, have, missing, isGoodMatch: pct >= 40 };
}

export function sortMatches(matches: RecipeMatch[], order: 'match' | 'urgent' | 'time'): RecipeMatch[] {
  const copy = [...matches];
  if (order === 'match') copy.sort((a, b) => b.pct - a.pct);
  if (order === 'urgent') copy.sort((a, b) => b.hits - a.hits || b.pct - a.pct);
  if (order === 'time') copy.sort((a, b) => parseInt(a.recipe.time, 10) - parseInt(b.recipe.time, 10));
  return copy;
}

/** 재고에서 소진되는(다 써서 빠지는) 필수 재료 이름 목록 — 실제 재고에 적힌 이름 기준 */
export function ingredientsToConsume(recipe: RecipeDef, items: InventoryItem[]): string[] {
  const names = items.map((i) => i.name);
  const consumed: string[] = [];
  for (const u of recipe.uses) {
    if (!u.essential) continue;
    const matched = findMatchingName(u.name, names);
    if (matched) consumed.push(matched);
  }
  return consumed;
}

const QTY_PATTERN = /^([\d.]+)(.*)$/;

export function bumpQuantity(quantity: string, delta: number): string {
  const match = QTY_PATTERN.exec(quantity);
  if (!match) return quantity;
  const value = Math.max(0, parseFloat(match[1]) + delta);
  return `${value}${match[2]}`;
}

export type CalendarDay = {
  key: string;
  date: string | null;
  label: string;
  mealCount: number;
  isToday: boolean;
};

/** month는 0-indexed(JS Date 관례) */
export function buildMonthGrid(year: number, month: number, meals: MealLogEntry[], today: Date): CalendarDay[] {
  const counts = new Map<string, number>();
  for (const meal of meals) {
    counts.set(meal.date, (counts.get(meal.date) ?? 0) + 1);
  }
  const todayKey = toDateKey(today);
  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const cells: CalendarDay[] = [];
  for (let i = 0; i < firstWeekday; i++) {
    cells.push({ key: `blank-${i}`, date: null, label: '', mealCount: 0, isToday: false });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const date = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push({
      key: date,
      date,
      label: String(d),
      mealCount: counts.get(date) ?? 0,
      isToday: date === todayKey,
    });
  }
  return cells;
}

/** 기록 시각 기준으로 아침/점심/저녁 슬롯을 정한다 — 05~10시 아침, 11~16시 점심, 그 외 저녁. */
export function mealSlotForTime(date: Date = new Date()): MealSlot {
  const hour = date.getHours();
  if (hour >= 5 && hour < 11) return '아침';
  if (hour >= 11 && hour < 17) return '점심';
  return '저녁';
}

export function toDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function formatSelectedDateLabel(dateKey: string): string {
  const [, m, d] = dateKey.split('-').map((p) => parseInt(p, 10));
  const week = ['일', '월', '화', '수', '목', '금', '토'];
  const date = new Date(dateKey);
  return `${m}월 ${d}일 ${week[date.getDay()]}요일`;
}
