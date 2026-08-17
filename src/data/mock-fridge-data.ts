import type {
  DoorStatus,
  FoodItem,
  GasStatus,
  NotificationDigest,
  RecipeSuggestion,
} from '@/types/fridge';

function daysFromNow(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString();
}

export const mockDoorStatus: DoorStatus = {
  isOpen: false,
  lastChangedAt: daysFromNow(0),
};

export const mockGasStatus: GasStatus = {
  level: 'normal',
  ppm: 412,
  lastUpdatedAt: daysFromNow(0),
};

// 우선순위(D-day 오름차순)로 미리 정렬되어 있지 않아도 화면에서 정렬합니다.
export const mockFoodItems: FoodItem[] = [
  {
    id: 'f1',
    name: '상추',
    thumbnailEmoji: '🥬',
    category: '채소',
    quantity: '1봉',
    addedAt: daysFromNow(-4),
    expiresAt: daysFromNow(-1),
  },
  {
    id: 'f2',
    name: '우유',
    thumbnailEmoji: '🥛',
    category: '유제품',
    quantity: '900ml',
    addedAt: daysFromNow(-5),
    expiresAt: daysFromNow(1),
  },
  {
    id: 'f3',
    thumbnailEmoji: '🍗',
    category: '육류',
    quantity: '2팩',
    addedAt: daysFromNow(-2),
    expiresAt: daysFromNow(2),
  },
  {
    id: 'f4',
    name: '계란',
    thumbnailEmoji: '🥚',
    category: '유제품',
    quantity: '10구',
    addedAt: daysFromNow(-6),
    expiresAt: daysFromNow(4),
  },
  {
    id: 'f5',
    name: '두부',
    thumbnailEmoji: '🧈',
    category: '가공식품',
    quantity: '1모',
    addedAt: daysFromNow(-1),
    expiresAt: daysFromNow(5),
  },
  {
    id: 'f6',
    thumbnailEmoji: '🍎',
    category: '과일',
    quantity: '4개',
    addedAt: daysFromNow(-3),
    expiresAt: daysFromNow(9),
  },
  {
    id: 'f7',
    name: '고추장',
    thumbnailEmoji: '🌶️',
    category: '가공식품',
    quantity: '1통',
    addedAt: daysFromNow(-30),
    expiresAt: daysFromNow(60),
  },
];

export const mockNotifications: NotificationDigest[] = [
  {
    id: 'n1',
    date: daysFromNow(0),
    summary: '오늘 소비기한이 임박한 품목 3개가 있어요 — 상추, 우유, 닭가슴살',
    itemCount: 3,
    read: false,
  },
  {
    id: 'n2',
    date: daysFromNow(-1),
    summary: '어제 새로 등록된 품목 2개 — 두부, 계란',
    itemCount: 2,
    read: false,
  },
  {
    id: 'n3',
    date: daysFromNow(-2),
    summary: '가스 센서 수치가 일시적으로 상승했다가 정상으로 돌아왔어요',
    itemCount: 0,
    read: true,
  },
];

export const mockRecipes: RecipeSuggestion[] = [
  {
    id: 'r1',
    name: '상추 계란 볶음밥',
    emoji: '🍳',
    usesIngredients: ['상추', '계란'],
    missingIngredients: ['밥'],
    cookTimeMinutes: 15,
  },
  {
    id: 'r2',
    name: '우유 크림 파스타',
    emoji: '🍝',
    usesIngredients: ['우유', '두부'],
    missingIngredients: ['파스타면'],
    cookTimeMinutes: 20,
  },
  {
    id: 'r3',
    name: '닭가슴살 두부 샐러드',
    emoji: '🥗',
    usesIngredients: ['닭가슴살', '두부', '상추'],
    missingIngredients: [],
    cookTimeMinutes: 10,
  },
];
