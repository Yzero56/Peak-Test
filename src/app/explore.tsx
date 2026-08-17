import { Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { FoodItemRow } from '@/components/dashboard/food-item-row';
import { SectionHeader } from '@/components/dashboard/section-header';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { mockFoodItems } from '@/data/mock-fridge-data';
import type { FoodCategory } from '@/types/fridge';
import { getDday } from '@/utils/dday';

// 웹에서는 app-tabs.web.tsx의 플로팅 상단 내비게이션 바와 겹치지 않도록 여백을 더 둡니다.
const contentPadding = Platform.select({
  web: { paddingTop: Spacing.six + Spacing.three, paddingBottom: Spacing.four },
  default: { paddingTop: Spacing.two, paddingBottom: BottomTabInset + Spacing.three },
});

function groupByCategory(items: typeof mockFoodItems) {
  const groups = new Map<FoodCategory, typeof mockFoodItems>();
  for (const item of items) {
    const list = groups.get(item.category) ?? [];
    list.push(item);
    groups.set(item.category, list);
  }
  return [...groups.entries()].map(([category, categoryItems]) => ({
    category,
    items: [...categoryItems].sort((a, b) => getDday(a.expiresAt) - getDday(b.expiresAt)),
  }));
}

export default function IngredientsScreen() {
  const groups = groupByCategory(mockFoodItems);

  return (
    <SafeAreaView className="flex-1 bg-white dark:bg-black" edges={['top']}>
      <ScrollView
        className="flex-1"
        contentContainerClassName="gap-6 px-4"
        contentContainerStyle={contentPadding}
        showsVerticalScrollIndicator={false}>
        <View>
          <Text className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">
            식재료
          </Text>
          <Text className="text-sm text-neutral-400 dark:text-neutral-500">
            총 {mockFoodItems.length}개 · 카테고리별 보기
          </Text>
        </View>

        {groups.map((group) => (
          <View key={group.category} className="gap-3">
            <SectionHeader title={group.category} trailing={`${group.items.length}개`} />
            <View className="gap-2">
              {group.items.map((item) => (
                <FoodItemRow key={item.id} item={item} />
              ))}
            </View>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}
