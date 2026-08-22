import { useRouter } from 'expo-router';
import { Pressable, Text, View } from 'react-native';

import { IconAvatar } from '@/components/fridge/icon-avatar';
import { useFridge } from '@/state/fridge-store';
import { decorateItem } from '@/utils/fridge-logic';

export function ItemSheet() {
  const router = useRouter();
  const { items, sheetItemId, closeSheet, bumpSheetQty, removeSheetItem, setRecipeSort } = useFridge();

  if (sheetItemId == null) return null;
  const raw = items.find((i) => i.id === sheetItemId);
  if (!raw) return null;
  const item = decorateItem(raw);

  const cookWithThis = () => {
    closeSheet();
    setRecipeSort('urgent');
    router.push('/recipes');
  };

  return (
    <View className="absolute inset-0 z-40 justify-end bg-neutral-900/40">
      <Pressable className="absolute inset-0" onPress={closeSheet} />
      <View className="rounded-t-[28px] bg-surface px-5 pb-8 pt-5">
        <View className="mx-auto mb-4 h-1 w-9 rounded-full bg-neutral-300" />

        <View className="flex-row items-center justify-between gap-3">
          <View className="flex-row items-center gap-3">
            <IconAvatar emoji={item.emoji} bgClass={item.iconBgClass} size={44} fontSize={22} />
            <Text className="text-[23px] text-neutral-900">{item.name}</Text>
          </View>
          <View className={`rounded-full px-3 py-1.5 ${item.pill.containerClass}`}>
            <Text className={`text-xs ${item.pill.textClass}`}>{item.ddayLabel}</Text>
          </View>
        </View>
        <Text className="mt-2 text-xs text-neutral-500">
          {item.location} 보관 · {item.category} · 유통기한 {item.expiresAt}
        </Text>

        <View className="mt-4 flex-row items-center gap-3 rounded-2xl bg-white px-4 py-3.5 shadow-sm">
          <Text className="flex-1 text-[15.5px] text-neutral-900">수량</Text>
          <Pressable
            onPress={() => bumpSheetQty(-1)}
            className="h-9 w-9 items-center justify-center rounded-full bg-neutral-200">
            <Text className="text-[17px] text-neutral-900">−</Text>
          </Pressable>
          <Text className="min-w-[58px] text-center text-[16.5px] text-neutral-900">{item.quantity}</Text>
          <Pressable
            onPress={() => bumpSheetQty(1)}
            className="h-9 w-9 items-center justify-center rounded-full bg-neutral-200">
            <Text className="text-[17px] text-neutral-900">＋</Text>
          </Pressable>
        </View>

        <View className="mt-3.5 flex-row gap-2.5">
          <Pressable onPress={removeSheetItem} className="flex-1 rounded-full bg-neutral-200 px-4 py-3.5">
            <Text className="text-center text-[14.5px] text-neutral-900">다 썼어요</Text>
          </Pressable>
          <Pressable onPress={cookWithThis} className="flex-[1.3] rounded-full bg-accent-600 px-4 py-3.5 shadow-sm">
            <Text className="text-center text-[17px] font-bold text-white">이걸로 요리하기</Text>
          </Pressable>
        </View>

        <Pressable onPress={closeSheet} className="mt-2.5 items-center py-2.5">
          <Text className="text-[13.5px] text-neutral-500">닫기</Text>
        </Pressable>
      </View>
    </View>
  );
}
