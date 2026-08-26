import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';

import { Chip } from '@/components/fridge/chip';
import { DateField } from '@/components/fridge/date-field';
import { IconAvatar } from '@/components/fridge/icon-avatar';
import { categoryOptions, locationOptions } from '@/data/mock-fridge-data';
import { useFridge } from '@/state/fridge-store';
import type { Category, Location } from '@/types/fridge';
import { decorateItem } from '@/utils/fridge-logic';

export function ItemSheet() {
  const router = useRouter();
  const { items, sheetItemId, closeSheet, bumpSheetQty, updateSheetItem, removeSheetItem, setRecipeSort } =
    useFridge();

  const [editing, setEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [categoryDraft, setCategoryDraft] = useState<Category>('기타');
  const [locationDraft, setLocationDraft] = useState<Location>('냉장');
  const [expiresAtDraft, setExpiresAtDraft] = useState('');

  const raw = items.find((i) => i.id === sheetItemId);

  useEffect(() => {
    setEditing(false);
  }, [sheetItemId]);

  if (sheetItemId == null || !raw) return null;
  const item = decorateItem(raw);

  const startEditing = () => {
    setNameDraft(raw.name);
    setCategoryDraft(raw.category);
    setLocationDraft(raw.location);
    setExpiresAtDraft(raw.expiresAt);
    setEditing(true);
  };

  const saveEditing = () => {
    updateSheetItem({
      name: nameDraft.trim() || raw.name,
      category: categoryDraft,
      location: locationDraft,
      expiresAt: expiresAtDraft,
    });
    setEditing(false);
  };

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

        {editing ? (
          <>
            <TextInput
              className="min-h-[44px] rounded-xl bg-neutral-100 px-3 text-[17px] text-neutral-900"
              value={nameDraft}
              onChangeText={setNameDraft}
              placeholder="재료 이름"
              placeholderTextColor="#a8adaa"
            />

            <Text className="mb-2 mt-3.5 text-xs text-neutral-500">유통기한</Text>
            <DateField value={expiresAtDraft} onChange={setExpiresAtDraft} />

            <Text className="mb-2 mt-3.5 text-xs text-neutral-500">분류</Text>
            <View className="flex-row flex-wrap gap-1.5">
              {categoryOptions.map((c) => (
                <Chip key={c} label={c} active={categoryDraft === c} onPress={() => setCategoryDraft(c)} />
              ))}
            </View>

            <Text className="mb-2 mt-3.5 text-xs text-neutral-500">보관 위치</Text>
            <View className="flex-row gap-1.5">
              {locationOptions.map((l) => (
                <Chip key={l} label={l} active={locationDraft === l} onPress={() => setLocationDraft(l)} />
              ))}
            </View>

            <View className="mt-4 flex-row gap-2.5">
              <Pressable onPress={() => setEditing(false)} className="flex-1 rounded-full bg-neutral-200 px-4 py-3.5">
                <Text className="text-center text-[14.5px] text-neutral-900">취소</Text>
              </Pressable>
              <Pressable onPress={saveEditing} className="flex-[1.3] rounded-full bg-accent-600 px-4 py-3.5 shadow-sm">
                <Text className="text-center text-[15.5px] font-bold text-white">저장</Text>
              </Pressable>
            </View>
          </>
        ) : (
          <>
            <View className="flex-row items-center justify-between gap-3">
              <View className="flex-row items-center gap-3">
                <IconAvatar emoji={item.emoji} bgClass={item.iconBgClass} size={44} fontSize={22} />
                <Text className="text-[23px] text-neutral-900">{item.name}</Text>
              </View>
              <View className={`shrink-0 rounded-full px-3 py-1.5 ${item.pill.containerClass}`}>
                <Text numberOfLines={1} className={`text-xs ${item.pill.textClass}`}>
                  {item.ddayLabel}
                </Text>
              </View>
            </View>
            <View className="mt-2 flex-row items-center justify-between">
              <Text className="text-xs text-neutral-500">
                {item.location} 보관 · {item.category} · 유통기한 {item.expiresAt}
              </Text>
              <Pressable onPress={startEditing}>
                <Text className="text-xs text-accent-700">수정</Text>
              </Pressable>
            </View>

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
          </>
        )}
      </View>
    </View>
  );
}
