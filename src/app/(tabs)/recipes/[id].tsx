import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMemo } from 'react';
import { Platform, Pressable, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useFridge } from '@/state/fridge-store';
import { decorateItem, ingredientMatches, mealSlotForTime } from '@/utils/fridge-logic';

export default function RecipeDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { items, recipeCatalog, cookRecipe } = useFridge();

  const recipe = recipeCatalog.find((r) => r.id === id);
  const decorated = useMemo(() => items.map((i) => decorateItem(i)), [items]);

  if (!recipe) {
    return (
      <SafeAreaView className="flex-1 items-center justify-center bg-surface">
        <Text className="text-neutral-500">레시피를 찾을 수 없어요</Text>
      </SafeAreaView>
    );
  }

  const have = recipe.uses.filter((u) => decorated.some((i) => ingredientMatches(u.name, i.name))).length;
  const matchPct = Math.round((have / recipe.uses.length) * 100);

  const handleCook = () => {
    cookRecipe(recipe);
    router.push('/meals');
  };

  return (
    <SafeAreaView className="flex-1 bg-surface" edges={['top']}>
      <View className="px-5 pt-2">
        <Pressable
          onPress={() => router.back()}
          className="h-[34px] w-[34px] items-center justify-center rounded-full bg-neutral-200">
          <Text className="text-[15px] text-neutral-900">←</Text>
        </Pressable>
        <Text className="mt-3.5 text-[25px] font-bold text-neutral-900">{recipe.title}</Text>
        <View className="mt-2.5 flex-row flex-wrap gap-1.5">
          <Tag label={recipe.level} />
          <Tag label={`${recipe.kcal}kcal`} />
          <Tag label={`매칭 ${matchPct}%`} accent />
        </View>
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{
          paddingHorizontal: 20,
          paddingTop: 20,
          paddingBottom: Platform.select({ web: 32, default: 130 }),
        }}
        showsVerticalScrollIndicator={false}>
        <View className="rounded-[22px] bg-white px-4 pb-2.5 pt-1.5 shadow-sm">
          <Text className="px-0 pb-1 pt-3 text-sm text-neutral-900">재료</Text>
          {recipe.uses.map((u) => {
            const owned = decorated.find((i) => ingredientMatches(u.name, i.name));
            const urgentOwned = owned != null && owned.dday <= 1;
            const status = owned ? (urgentOwned ? '먼저 쓰기' : '있어요') : '없어요';
            const tone = owned
              ? urgentOwned
                ? { bg: 'bg-amber-200', text: 'text-amber-950' }
                : { bg: 'bg-neutral-200', text: 'text-neutral-800' }
              : { bg: 'bg-neutral-100', text: 'text-neutral-500' };
            return (
              <View key={u.name} className="flex-row items-center gap-2.5 py-2.5">
                <Text className={`flex-1 text-[15.5px] ${owned ? 'text-neutral-900' : 'text-neutral-500'}`}>
                  {u.name}
                </Text>
                <Text className="text-xs text-neutral-500">{u.amount}</Text>
                <View className={`min-w-[58px] items-center rounded-full px-2.5 py-1.5 ${tone.bg}`}>
                  <Text className={`text-[11.5px] ${tone.text}`}>{status}</Text>
                </View>
              </View>
            );
          })}
        </View>
        <Text className="mt-3.5 px-1 text-[13px] leading-5 text-neutral-600">{recipe.note}</Text>

        <Text className="mb-2.5 mt-6 px-1 text-sm text-neutral-900">조리 순서</Text>
        <View className="gap-2">
          {recipe.steps.map((step, i) => (
            <View key={i} className="flex-row gap-3 rounded-2xl bg-white px-4 py-3.5 shadow-sm">
              <View className="h-[23px] w-[23px] items-center justify-center rounded-full bg-accent-100">
                <Text className="text-[12.5px] text-accent-800">{i + 1}</Text>
              </View>
              <Text className="flex-1 text-[15px] leading-6 text-neutral-900">{step}</Text>
            </View>
          ))}
        </View>
      </ScrollView>

      <View
        className="absolute inset-x-0 bottom-0 bg-surface px-5 pb-6 pt-3.5"
        style={Platform.select({ web: { position: 'relative' as const }, default: {} })}>
        <Text className="mb-2.5 text-center text-xs text-neutral-500">
          완료하면 재료가 빠지고 오늘 {mealSlotForTime()} 식단에 기록돼요
        </Text>
        <Pressable onPress={handleCook} className="rounded-full bg-accent-600 py-4 shadow-md">
          <Text className="text-center text-[17px] font-bold text-white">다 만들었어요</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

function Tag({ label, accent }: { label: string; accent?: boolean }) {
  return (
    <View className={`rounded-full px-2.5 py-1.5 ${accent ? 'bg-accent-100' : 'bg-neutral-200'}`}>
      <Text className={`text-xs ${accent ? 'text-accent-800' : 'text-neutral-800'}`}>{label}</Text>
    </View>
  );
}
