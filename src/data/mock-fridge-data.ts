import type {
  Category,
  InventoryItem,
  Location,
  MealLogEntry,
  RecipeDef,
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

export const recipeCatalog: RecipeDef[] = [
  {
    id: 'r1', title: '대파 계란 볶음밥', time: '15분', level: '쉬움', kcal: 540,
    note: '대파를 기름에 먼저 볶아 파기름을 내면 향이 훨씬 좋아요.',
    uses: [
      { name: '대파', amount: '1대', essential: true },
      { name: '계란', amount: '2개', essential: false },
      { name: '당근', amount: '1/2개', essential: false },
      { name: '밥', amount: '1공기', essential: false },
    ],
    steps: [
      '대파를 송송 썰어 약불에서 천천히 볶아 파기름을 내요.',
      '당근을 잘게 다져 넣고 2분 볶아요.',
      '계란을 풀어 넣고 반숙으로 스크램블해요.',
      '밥을 넣고 센 불에서 고루 볶은 뒤 소금·후추로 간해요.',
    ],
  },
  {
    id: 'r2', title: '애호박 된장찌개', time: '20분', level: '쉬움', kcal: 320,
    note: '두부는 맨 마지막에 넣어야 부서지지 않아요.',
    uses: [
      { name: '애호박', amount: '1개', essential: true },
      { name: '두부', amount: '1/2모', essential: false },
      { name: '대파', amount: '1/2대', essential: false },
      { name: '된장', amount: '1큰술', essential: false },
    ],
    steps: [
      '쌀뜨물 400ml에 된장을 풀어 끓여요.',
      '애호박을 반달 모양으로 썰어 넣어요.',
      '5분 뒤 두부를 넣고 3분 더 끓여요.',
      '대파를 올리고 불을 꺼요.',
    ],
  },
  {
    id: 'r3', title: '우유 프렌치토스트', time: '10분', level: '쉬움', kcal: 430,
    note: '남은 우유와 식빵을 한 번에 정리할 수 있어요.',
    uses: [
      { name: '우유', amount: '200ml', essential: true },
      { name: '계란', amount: '2개', essential: false },
      { name: '식빵', amount: '3장', essential: true },
      { name: '버터', amount: '10g', essential: false },
    ],
    steps: [
      '우유와 계란을 섞어 달걀물을 만들어요.',
      '식빵을 앞뒤로 30초씩 적셔요.',
      '버터를 두른 팬에 중약불로 2분씩 구워요.',
    ],
  },
  {
    id: 'r4', title: '닭가슴살 채소볶음', time: '25분', level: '보통', kcal: 480,
    note: '닭가슴살은 미리 꺼내 해동해 두면 편해요.',
    uses: [
      { name: '닭가슴살', amount: '200g', essential: true },
      { name: '파프리카', amount: '1개', essential: false },
      { name: '양파', amount: '1/2개', essential: false },
      { name: '당근', amount: '1/2개', essential: false },
    ],
    steps: [
      '닭가슴살을 한입 크기로 썰어 소금·후추로 밑간해요.',
      '센 불에 겉면을 노릇하게 익혀요.',
      '채소를 넣고 3분 볶아요.',
      '간장 1큰술로 마무리해요.',
    ],
  },
  {
    id: 'r5', title: '시금치 나물', time: '10분', level: '쉬움', kcal: 90,
    note: '데친 뒤 찬물에 헹구면 색이 예쁘게 살아요.',
    uses: [
      { name: '시금치', amount: '1봉', essential: true },
      { name: '마늘', amount: '1쪽', essential: false },
      { name: '참기름', amount: '1작은술', essential: false },
    ],
    steps: [
      '끓는 물에 소금을 넣고 시금치를 30초 데쳐요.',
      '찬물에 헹궈 물기를 꼭 짜요.',
      '다진 마늘·참기름·소금으로 조물조물 무쳐요.',
    ],
  },
  {
    id: 'r6', title: '연어 스테이크', time: '20분', level: '보통', kcal: 610,
    note: '껍질 쪽을 먼저 오래 구워야 바삭해요.',
    uses: [
      { name: '연어', amount: '2토막', essential: true },
      { name: '버터', amount: '15g', essential: false },
      { name: '레몬', amount: '1/2개', essential: false },
    ],
    steps: [
      '연어의 물기를 닦고 소금·후추를 뿌려요.',
      '껍질 쪽부터 중강불로 4분 구워요.',
      '뒤집어 2분 굽고 버터를 끼얹어요.',
      '레몬을 곁들여 내요.',
    ],
  },
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
