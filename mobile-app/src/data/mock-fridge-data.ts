import type {
  Category,
  InventoryItem,
  Location,
  MealLogEntry,
  ScanCandidate,
} from '@/types/fridge';

function daysFromNow(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export const initialInventory: InventoryItem[] = [
  { id: 1, name: '대파', category: '채소', quantity: '1단', expiresAt: daysFromNow(0), location: '냉장' },
  { id: 2, name: '우유', category: '유제품', quantity: '900ml', expiresAt: daysFromNow(0), location: '냉장' },
  { id: 3, name: '애호박', category: '채소', quantity: '1개', expiresAt: daysFromNow(1), location: '냉장' },
  { id: 4, name: '닭가슴살', category: '육류·계란', quantity: '400g', expiresAt: daysFromNow(1), location: '냉동' },
  { id: 5, name: '식빵', category: '기타', quantity: '반 봉', expiresAt: daysFromNow(1), location: '실온' },
  { id: 6, name: '시금치', category: '채소', quantity: '1봉', expiresAt: daysFromNow(2), location: '냉장' },
  { id: 7, name: '연어', category: '수산물', quantity: '2토막', expiresAt: daysFromNow(2), location: '냉장' },
  { id: 8, name: '플레인요거트', category: '유제품', quantity: '4개', expiresAt: daysFromNow(3), location: '냉장' },
  { id: 9, name: '파프리카', category: '채소', quantity: '2개', expiresAt: daysFromNow(4), location: '냉장' },
  { id: 10, name: '두부', category: '기타', quantity: '1모', expiresAt: daysFromNow(5), location: '냉장' },
  { id: 11, name: '계란', category: '육류·계란', quantity: '8구', expiresAt: daysFromNow(7), location: '냉장' },
  { id: 12, name: '당근', category: '채소', quantity: '2개', expiresAt: daysFromNow(9), location: '냉장' },
  { id: 13, name: '양파', category: '채소', quantity: '3개', expiresAt: daysFromNow(16), location: '실온' },
  { id: 14, name: '버터', category: '유제품', quantity: '200g', expiresAt: daysFromNow(29), location: '냉장' },
];

export const initialMeals: MealLogEntry[] = [
  { date: daysFromNow(-17), slot: '저녁', title: '애호박 된장찌개', kcal: 320 },
  { date: daysFromNow(-15), slot: '아침', title: '우유 프렌치토스트', kcal: 430 },
  { date: daysFromNow(-15), slot: '저녁', title: '닭가슴살 채소볶음', kcal: 480 },
  { date: daysFromNow(-13), slot: '점심', title: '대파 계란 볶음밥', kcal: 540 },
  { date: daysFromNow(-11), slot: '저녁', title: '연어 스테이크', kcal: 610 },
  { date: daysFromNow(-9), slot: '점심', title: '시금치 나물', kcal: 90 },
  { date: daysFromNow(-9), slot: '저녁', title: '애호박 된장찌개', kcal: 320 },
  { date: daysFromNow(-7), slot: '아침', title: '우유 프렌치토스트', kcal: 430 },
  { date: daysFromNow(-6), slot: '저녁', title: '대파 계란 볶음밥', kcal: 540 },
  { date: daysFromNow(-4), slot: '점심', title: '닭가슴살 채소볶음', kcal: 480 },
  { date: daysFromNow(-3), slot: '저녁', title: '연어 스테이크', kcal: 610 },
  { date: daysFromNow(-2), slot: '아침', title: '우유 프렌치토스트', kcal: 430 },
  { date: daysFromNow(-1), slot: '저녁', title: '애호박 된장찌개', kcal: 320 },
  { date: daysFromNow(0), slot: '아침', title: '시금치 나물', kcal: 90 },
];

export const quickAddNames: string[] = [
  '계란', '우유', '두부', '양파', '대파', '마늘', '감자', '김치', '식빵', '요거트', '닭가슴살', '토마토',
];

export const scanCandidates: ScanCandidate[] = [
  { name: '방울토마토', quantity: '1팩', expiresAt: daysFromNow(6), category: '채소', location: '냉장' },
  { name: '모짜렐라 치즈', quantity: '200g', expiresAt: daysFromNow(13), category: '유제품', location: '냉장' },
  { name: '삼겹살', quantity: '500g', expiresAt: daysFromNow(3), category: '육류·계란', location: '냉장' },
];

export const categoryOptions: Category[] = ['채소', '육류·계란', '유제품', '수산물', '기타'];
export const locationOptions: Location[] = ['냉장', '냉동', '실온'];
