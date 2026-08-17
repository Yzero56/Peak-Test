export type DoorStatus = {
  isOpen: boolean;
  lastChangedAt: string; // ISO timestamp
};

export type GasLevel = 'normal' | 'caution' | 'danger';

export type GasStatus = {
  level: GasLevel;
  ppm: number;
  lastUpdatedAt: string; // ISO timestamp
};

export type FoodCategory = '채소' | '과일' | '유제품' | '육류' | '수산물' | '가공식품' | '기타';

export type FoodItem = {
  id: string;
  /** 사용자가 이름을 지정하지 않은 경우 undefined — 이 때는 썸네일로 표시 */
  name?: string;
  thumbnailEmoji: string;
  category: FoodCategory;
  quantity: string;
  addedAt: string; // ISO date
  expiresAt: string; // ISO date
};

export type NotificationDigest = {
  id: string;
  date: string; // ISO date, 요약이 발송된 날짜
  summary: string;
  itemCount: number;
  read: boolean;
};

export type RecipeSuggestion = {
  id: string;
  name: string;
  emoji: string;
  usesIngredients: string[];
  missingIngredients: string[];
  cookTimeMinutes: number;
};
