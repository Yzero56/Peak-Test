export type Category = '채소' | '육류·계란' | '유제품' | '수산물' | '기타';

export type Location = '냉장' | '냉동' | '실온';

export type InventoryItem = {
  id: number;
  name: string;
  category: Category;
  quantity: string;
  expiresAt: string; // ISO date (YYYY-MM-DD)
  location: Location;
};

export type RecipeIngredient = {
  name: string;
  amount: string;
  /** 이 재료를 다 쓰면 재고에서 완전히 빠지는 핵심 재료인지 여부 */
  essential: boolean;
};

export type RecipeDef = {
  id: string;
  title: string;
  time: string;
  level: string;
  kcal: number;
  note: string;
  uses: RecipeIngredient[];
  steps: string[];
};

export type MealLogEntry = {
  date: string; // ISO date (YYYY-MM-DD)
  slot: '아침' | '점심' | '저녁';
  title: string;
  kcal: number;
};

export type NotificationLeadTime = '1일 전' | '3일 전' | '7일 전';

export type NotificationToggles = {
  urgent: boolean;
  low: boolean;
  digest: boolean;
  plan: boolean;
};

export type NotificationSettings = {
  leadTime: NotificationLeadTime;
  toggles: NotificationToggles;
};

export type RecipeSortOrder = 'match' | 'urgent' | 'time';

export type InventoryViewMode = 'exp' | 'name' | 'cat';

export type AddMode = 'manual' | 'photo' | 'quick';

export type ManualAddForm = {
  name: string;
  quantity: string;
  expiresAt: string;
  category: Category;
  location: Location;
};

export type ScanCandidate = {
  name: string;
  quantity: string;
  expiresAt: string;
  category: Category;
  location: Location;
};

export type ToastState = {
  message: string;
  actionLabel: string;
  onAction: () => void;
};
