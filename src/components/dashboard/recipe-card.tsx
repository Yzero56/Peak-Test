import { Text, View } from 'react-native';

import type { RecipeSuggestion } from '@/types/fridge';

export function RecipeCard({ recipe }: { recipe: RecipeSuggestion }) {
  return (
    <View className="gap-3 rounded-2xl bg-neutral-100 p-4 dark:bg-neutral-900">
      <View className="flex-row items-center gap-3">
        <Text className="text-3xl">{recipe.emoji}</Text>
        <View className="flex-1">
          <Text className="text-base font-semibold text-neutral-900 dark:text-neutral-50">
            {recipe.name}
          </Text>
          <Text className="text-xs text-neutral-400 dark:text-neutral-500">
            조리 시간 약 {recipe.cookTimeMinutes}분
          </Text>
        </View>
      </View>

      <View className="flex-row flex-wrap gap-1.5">
        {recipe.usesIngredients.map((ingredient) => (
          <View
            key={ingredient}
            className="rounded-full bg-emerald-100 px-2.5 py-1 dark:bg-emerald-950">
            <Text className="text-xs font-medium text-emerald-700 dark:text-emerald-400">
              냉장고에 있음 · {ingredient}
            </Text>
          </View>
        ))}
        {recipe.missingIngredients.map((ingredient) => (
          <View
            key={ingredient}
            className="rounded-full bg-neutral-200 px-2.5 py-1 dark:bg-neutral-800">
            <Text className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
              구매 필요 · {ingredient}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}
