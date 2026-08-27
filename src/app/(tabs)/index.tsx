import { useRouter } from 'expo-router';
import { useMemo } from 'react';
import { Platform, Pressable, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Chip } from '@/components/fridge/chip';
import { InventoryRow } from '@/components/fridge/inventory-row';
import { RecipeHeroCard } from '@/components/fridge/recipe-hero-card';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { useFridge } from '@/state/fridge-store';
import type { InventoryViewMode } from '@/types/fridge';
import { decorateItem, groupByCategory, matchRecipe, sortMatches } from '@/utils/fridge-logic';

const contentPadding = Platform.select({
  web: { paddingTop: Spacing.six + Spacing.three, paddingBottom: Spacing.four },
  default: { paddingTop: Spacing.two, paddingBottom: BottomTabInset + Spacing.three },
});

const todayLabel = new Date().toLocaleDateString('ko-KR', {
  month: 'long',
  day: 'numeric',
  weekday: 'short',
});

const VIEW_OPTIONS: { key: InventoryViewMode; label: string }[] = [
  { key: 'exp', label: '기한순' },
  { key: 'name', label: '이름순' },
  { key: 'cat', label: '분류별' },
];

export default function HomeScreen() {
  const router = useRouter();
  const { items, recipeCatalog, inventoryView, setInventoryView, openSheet, setRecipeSort, climate } = useFridge();

  const climateLabel = `${climate.temperatureC != null ? `${climate.temperatureC.toFixed(1)}°C` : '-'} · 습도 ${
    climate.humidityPct != null ? `${Math.round(climate.humidityPct)}%` : '-'
  }`;

  const decorated = useMemo(
    () => items.map((i) => decorateItem(i)).sort((a, b) => a.dday - b.dday),
    [items],
  );
  const urgent = decorated.filter((i) => i.dday <= 1);
  const heroWords = urgent.length > 0 ? urgent.map((i) => i.name) : [decorated[0]?.name].filter((n): n is string => !!n);
  const heroPre = urgent.length > 0 ? '오늘은 ' : '지금은 ';
  const heroPost = urgent.length > 0 ? '부터 쓰면 좋아요' : ' 하나만 챙기면 돼요';
  const heroSub =
    urgent.length > 0
      ? `오늘까지 ${urgent.length}개 · 이번 주 안에 ${decorated.filter((i) => i.dday > 1 && i.dday <= 7).length}개`
      : '오늘까지 써야 할 재료는 없어요';

  const matches = useMemo(
    () => sortMatches(recipeCatalog.map((r) => matchRecipe(r, decorated)), 'urgent').slice(0, 3),
    [decorated, recipeCatalog],
  );
  // 목업 레시피(재료 3~4개) 기준이던 50%는 API 레시피(평균 재료 9~10개)엔 너무 빡빡해서 25%로 낮췄다.
  const cookableCount = useMemo(
    () => recipeCatalog.map((r) => matchRecipe(r, decorated)).filter((m) => m.pct >= 25).length,
    [decorated, recipeCatalog],
  );

  const orderedItems =
    inventoryView === 'name' ? [...decorated].sort((a, b) => a.name.localeCompare(b.name, 'ko')) : decorated;
  const groups = inventoryView === 'cat' ? groupByCategory(decorated) : [];

  return (
    <SafeAreaView className="flex-1 bg-surface" edges={['top']}>
      <ScrollView
        className="flex-1"
        contentContainerStyle={contentPadding}
        showsVerticalScrollIndicator={false}>
        <View className="gap-1 px-5">
          <View className="flex-row items-center justify-between gap-3">
            <View className="flex-row items-baseline gap-2">
              <Text className="text-[17px] font-bold text-neutral-900">우리집 냉장고</Text>
              <Text className="text-xs text-neutral-500">{todayLabel}</Text>
            </View>
            <Pressable
              onPress={() => router.push('/add')}
              className="rounded-full bg-accent-600 px-4 py-2.5 shadow-sm">
              <Text className="text-[14.5px] font-bold text-white">＋ 추가</Text>
            </Pressable>
          </View>

          <Text className="mt-1 text-xs text-neutral-500">{climateLabel}</Text>

          <Text className="mt-5 text-[25px] leading-8 text-neutral-900">
            {heroPre}
            {heroWords.map((name, idx) => (
              <Text key={`${name}-${idx}`}>
                <Text className="rounded-sm bg-amber-200 font-bold">{name}</Text>
                {idx < heroWords.length - 1 ? ', ' : ''}
              </Text>
            ))}
            {heroPost}
          </Text>
          <Text className="mt-2 text-[13px] text-neutral-600">{heroSub}</Text>

          <View className="mt-5 flex-row items-baseline justify-between">
            <Text className="text-[13px] font-bold text-neutral-900">추천 레시피</Text>
            <Pressable onPress={() => router.push('/recipes')}>
              <Text className="text-xs text-accent-700">전체 보기</Text>
            </Pressable>
          </View>
          {matches.length === 0 ? (
            <Text className="mt-2.5 text-[13px] text-neutral-400">
              레시피를 불러오지 못했어요 · 설정에서 백엔드 연결을 확인해주세요
            </Text>
          ) : (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ gap: 9, marginTop: 10, paddingBottom: 2 }}>
              {matches.map((m) => (
                <RecipeHeroCard
                  key={m.recipe.id}
                  match={m}
                  onPress={() => router.push(`/recipes/${m.recipe.id}`)}
                />
              ))}
            </ScrollView>
          )}
        </View>

        <View className="mt-6 rounded-t-[26px] bg-white px-[18px] pt-[18px]">
          <View className="flex-row items-center justify-between gap-2.5">
            <Text className="text-[19px] font-bold text-neutral-900">{decorated.length}개</Text>
            <View className="flex-row gap-0.5">
              {VIEW_OPTIONS.map((opt) => (
                <Chip
                  key={opt.key}
                  label={opt.label}
                  active={inventoryView === opt.key}
                  onPress={() => setInventoryView(opt.key)}
                  size="sm"
                />
              ))}
            </View>
          </View>

          <View className="mt-1.5 px-0.5">
            {inventoryView === 'cat' ? (
              groups.map((g) => (
                <View key={g.category} className="mt-5">
                  <View className="flex-row items-center justify-between">
                    <Text className="text-[15px] text-neutral-900">
                      {g.items[0]?.emoji} {g.category}
                    </Text>
                    <Text className="text-xs text-neutral-500">{g.items.length}가지</Text>
                  </View>
                  <View className="mt-1.5">
                    {g.items.map((it) => (
                      <InventoryRow key={it.id} item={it} onPress={() => openSheet(it.id)} />
                    ))}
                  </View>
                </View>
              ))
            ) : (
              <View>
                {orderedItems.map((it) => (
                  <InventoryRow key={it.id} item={it} onPress={() => openSheet(it.id)} />
                ))}
              </View>
            )}
          </View>

          <Pressable
            onPress={() => {
              setRecipeSort('match');
              router.push('/recipes');
            }}
            className="my-5 rounded-full bg-accent-600 px-4 py-4 shadow-sm">
            <Text className="text-center text-[17px] font-bold text-white">
              지금 만들 수 있는 요리 {cookableCount}가지
            </Text>
          </Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
