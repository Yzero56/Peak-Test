import { useRouter } from 'expo-router';
import { useMemo } from 'react';
import { Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Chip } from '@/components/fridge/chip';
import { RecipeListCard } from '@/components/fridge/recipe-list-card';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { useFridge } from '@/state/fridge-store';
import type { RecipeSortOrder } from '@/types/fridge';
import { decorateItem, matchRecipe, sortMatches } from '@/utils/fridge-logic';

const contentPadding = Platform.select({
  web: { paddingTop: Spacing.six + Spacing.three, paddingBottom: Spacing.four },
  default: { paddingTop: Spacing.two, paddingBottom: BottomTabInset + Spacing.three },
});

const todayLabel = new Date().toLocaleDateString('ko-KR', {
  month: 'long',
  day: 'numeric',
  weekday: 'short',
});

const SORT_OPTIONS: { key: RecipeSortOrder; label: string }[] = [
  { key: 'match', label: '매칭률순' },
  { key: 'urgent', label: '임박 재료순' },
  { key: 'time', label: '빠른 순' },
];

export default function RecipesScreen() {
  const router = useRouter();
  const { items, recipeCatalog, recipeSort, setRecipeSort } = useFridge();

  const decorated = useMemo(() => items.map((i) => decorateItem(i)), [items]);
  const matches = useMemo(
    () => sortMatches(recipeCatalog.map((r) => matchRecipe(r, decorated)), recipeSort),
    [decorated, recipeSort, recipeCatalog],
  );

  return (
    <SafeAreaView className="flex-1 bg-surface" edges={['top']}>
      <View className="px-5 pt-2.5">
        <Text className="text-xs text-neutral-500">{todayLabel}</Text>
        <Text className="mt-1.5 text-[26px] font-bold text-neutral-900">오늘 뭐 먹을까요?</Text>
        <View className="mt-3.5 flex-row gap-1.5">
          {SORT_OPTIONS.map((opt) => (
            <Chip key={opt.key} label={opt.label} active={recipeSort === opt.key} onPress={() => setRecipeSort(opt.key)} />
          ))}
        </View>
      </View>
      <ScrollView
        className="flex-1"
        contentContainerStyle={{ ...contentPadding, paddingHorizontal: 20, gap: 12 }}
        showsVerticalScrollIndicator={false}>
        {matches.length === 0 ? (
          <View className="items-center rounded-2xl bg-white px-4 py-[22px] shadow-sm">
            <Text className="text-center text-[13.5px] leading-5 text-neutral-500">
              레시피를 불러오지 못했어요{'\n'}설정에서 백엔드 연결을 확인해주세요
            </Text>
          </View>
        ) : (
          matches.map((m) => (
            <RecipeListCard key={m.recipe.id} match={m} onPress={() => router.push(`/recipes/${m.recipe.id}`)} />
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}
