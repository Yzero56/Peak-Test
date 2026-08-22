import { Pressable, Text, View } from 'react-native';

import type { RecipeMatch } from '@/utils/fridge-logic';

export function RecipeHeroCard({ match, onPress }: { match: RecipeMatch; onPress: () => void }) {
  const { recipe, hits, pct } = match;
  const useLabel = hits > 0 ? `임박 재료 ${hits}가지 사용` : '있는 재료로 충분';
  const useTone =
    hits > 0 ? { bg: 'bg-amber-100', text: 'text-amber-900' } : { bg: 'bg-neutral-200', text: 'text-neutral-800' };

  return (
    <Pressable
      onPress={onPress}
      className="w-[152px] rounded-2xl border border-divider bg-white p-3 shadow-sm">
      <View className={`self-start rounded-full px-2.5 py-1 ${useTone.bg}`}>
        <Text className={`text-[11px] font-semibold ${useTone.text}`}>{useLabel}</Text>
      </View>
      <Text className="mt-2.5 text-[15.5px] font-bold leading-5 text-neutral-900">{recipe.title}</Text>
      <Text className="mt-1.5 text-xs text-neutral-500">
        {recipe.time} · 매칭 {pct}%
      </Text>
    </Pressable>
  );
}
