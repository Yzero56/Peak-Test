import { Pressable, Text, View } from 'react-native';

import type { RecipeMatch } from '@/utils/fridge-logic';

export function RecipeListCard({ match, onPress }: { match: RecipeMatch; onPress: () => void }) {
  const { recipe, pct, hits, missing, isGoodMatch } = match;
  const kicker = hits > 0 ? `임박 재료 ${hits}가지 정리` : '있는 재료로 충분';
  const kickerTone = hits > 0 ? { bg: 'bg-amber-100', text: 'text-amber-800' } : { bg: 'bg-neutral-200', text: 'text-neutral-700' };
  const ringTone = isGoodMatch ? { bg: 'bg-accent-100', text: 'text-accent-800' } : { bg: 'bg-neutral-200', text: 'text-neutral-800' };
  const barTone = isGoodMatch ? 'bg-accent-600' : 'bg-neutral-400';
  const missingLabel = missing.length === 0 ? '더 필요한 재료 없음' : `더 필요한 재료 : ${missing.join(', ')}`;
  const missingTone = missing.length === 0 ? 'text-accent-700' : 'text-neutral-600';

  return (
    <Pressable onPress={onPress} className="rounded-[22px] bg-white p-4 shadow-sm">
      <View className="flex-row items-start gap-3">
        <View className="min-w-0 flex-1">
          <View className={`self-start rounded-full px-2.5 py-1.5 ${kickerTone.bg}`}>
            <Text className={`text-[11.5px] ${kickerTone.text}`}>{kicker}</Text>
          </View>
          <Text className="mt-2.5 text-[20px] font-bold leading-6 text-neutral-900">{recipe.title}</Text>
        </View>
        <View className={`h-14 w-14 items-center justify-center rounded-full ${ringTone.bg}`}>
          <Text className={`text-[17px] font-bold leading-5 ${ringTone.text}`}>{pct}%</Text>
          <Text className={`mt-0.5 text-[9.5px] ${ringTone.text}`}>매칭</Text>
        </View>
      </View>

      <View className="mt-3.5 h-1.5 overflow-hidden rounded-full bg-neutral-200">
        <View className={`h-1.5 rounded-full ${barTone}`} style={{ width: `${pct}%` }} />
      </View>

      <View className="mt-3 flex-row flex-wrap gap-x-3 gap-y-1.5">
        <Text className="text-xs text-neutral-500">{recipe.time}</Text>
        <Text className="text-xs text-neutral-500">·</Text>
        <Text className="text-xs text-neutral-500">{recipe.level}</Text>
        <Text className="text-xs text-neutral-500">·</Text>
        <Text className="text-xs text-neutral-500">{recipe.kcal}kcal</Text>
      </View>
      <Text className={`mt-2.5 text-xs leading-5 ${missingTone}`}>{missingLabel}</Text>
    </Pressable>
  );
}
