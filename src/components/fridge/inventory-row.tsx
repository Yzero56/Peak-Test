import { Pressable, Text, View } from 'react-native';

import { IconAvatar } from '@/components/fridge/icon-avatar';
import type { DecoratedItem } from '@/utils/fridge-logic';

export function InventoryRow({ item, onPress }: { item: DecoratedItem; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      className="flex-row items-center gap-3 border-b border-divider py-3">
      <IconAvatar emoji={item.emoji} bgClass={item.iconBgClass} />
      <View className="min-w-0 flex-1">
        <Text className="text-[16.5px] text-neutral-900">{item.name}</Text>
        <Text className="mt-1 text-xs text-neutral-500">{item.sub}</Text>
      </View>
      <View className={`shrink-0 items-center rounded-full px-2.5 py-1.5 ${item.pill.containerClass}`}>
        <Text numberOfLines={1} className={`text-xs ${item.pill.textClass}`}>
          {item.ddayLabel}
        </Text>
      </View>
    </Pressable>
  );
}
