import { Text, View } from 'react-native';

import type { FoodItem } from '@/types/fridge';
import { formatDday, freshnessStyles, getDday, getFreshnessStatus } from '@/utils/dday';

export function FoodItemRow({ item }: { item: FoodItem }) {
  const dday = getDday(item.expiresAt);
  const status = getFreshnessStatus(dday);
  const style = freshnessStyles[status];

  return (
    <View className="flex-row items-center gap-3 rounded-2xl bg-neutral-100 p-3 dark:bg-neutral-900">
      <View className="h-12 w-12 items-center justify-center rounded-xl bg-white dark:bg-neutral-800">
        <Text className="text-2xl">{item.thumbnailEmoji}</Text>
      </View>

      <View className="flex-1 gap-0.5">
        {item.name ? (
          <Text className="text-base font-medium text-neutral-900 dark:text-neutral-50">
            {item.name}
          </Text>
        ) : (
          <Text className="text-base font-medium text-neutral-400 dark:text-neutral-500">
            이름 미지정 · {item.category}
          </Text>
        )}
        <Text className="text-xs text-neutral-400 dark:text-neutral-500">
          {item.category} · {item.quantity}
        </Text>
      </View>

      <View className={`items-center rounded-full px-3 py-1.5 ${style.badge}`}>
        <Text className={`text-xs font-semibold ${style.badgeText}`}>{formatDday(dday)}</Text>
      </View>
    </View>
  );
}
