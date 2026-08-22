import { useRouter } from 'expo-router';
import type { ReactNode } from 'react';
import { Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Chip } from '@/components/fridge/chip';
import { IconAvatar } from '@/components/fridge/icon-avatar';
import { categoryOptions, locationOptions, quickAddNames, scanCandidates } from '@/data/mock-fridge-data';
import { useFridge } from '@/state/fridge-store';
import type { AddMode } from '@/types/fridge';
import { chipTone, ddayLabel, decorateItem, iconFor } from '@/utils/fridge-logic';

const MODE_OPTIONS: { key: AddMode; label: string }[] = [
  { key: 'manual', label: '직접 입력' },
  { key: 'photo', label: '사진으로' },
  { key: 'quick', label: '자주 쓰는' },
];

export default function AddScreen() {
  const router = useRouter();
  const {
    addMode,
    setAddMode,
    manualForm,
    updateManualForm,
    submitManualAdd,
    scanned,
    startScan,
    scanPicked,
    toggleScanPick,
    submitScanAdd,
    quickPicked,
    toggleQuickPick,
    submitQuickAdd,
  } = useFridge();

  const previewDday = manualForm.expiresAt ? ddayLabel(decorateItem({ ...manualForm, id: 0, name: '' }).dday) : null;

  const closeAfter = (didSubmit: boolean) => {
    if (didSubmit) router.back();
  };

  return (
    <SafeAreaView className="flex-1 bg-surface">
      <View className="px-5 pt-2">
        <Pressable
          onPress={() => router.back()}
          className="h-[34px] w-[34px] items-center justify-center rounded-full bg-neutral-200">
          <Text className="text-[15px] text-neutral-900">←</Text>
        </Pressable>
        <Text className="mt-3.5 text-[25px] font-bold text-neutral-900">무엇을 넣을까요?</Text>
        <View className="mt-3.5 flex-row gap-1.5">
          {MODE_OPTIONS.map((opt) => (
            <Chip key={opt.key} label={opt.label} active={addMode === opt.key} onPress={() => setAddMode(opt.key)} />
          ))}
        </View>
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 18, paddingBottom: 24 }}
        showsVerticalScrollIndicator={false}>
        {addMode === 'manual' ? (
          <>
            <View className="gap-4 rounded-[22px] bg-white p-[18px] shadow-sm">
              <Field label="재료 이름">
                <TextInput
                  className="min-h-[44px] rounded-xl bg-neutral-100 px-3 text-[15px] text-neutral-900"
                  placeholder="예: 애호박"
                  placeholderTextColor="#a8adaa"
                  value={manualForm.name}
                  onChangeText={(v) => updateManualForm({ name: v })}
                />
              </Field>
              <View className="flex-row gap-3">
                <View className="flex-1">
                  <Field label="수량">
                    <TextInput
                      className="min-h-[44px] rounded-xl bg-neutral-100 px-3 text-[15px] text-neutral-900"
                      placeholder="2개"
                      placeholderTextColor="#a8adaa"
                      value={manualForm.quantity}
                      onChangeText={(v) => updateManualForm({ quantity: v })}
                    />
                  </Field>
                </View>
                <View className="flex-1">
                  <Field label="유통기한">
                    <TextInput
                      className="min-h-[44px] rounded-xl bg-neutral-100 px-3 text-[15px] text-neutral-900"
                      placeholder="YYYY-MM-DD"
                      placeholderTextColor="#a8adaa"
                      value={manualForm.expiresAt}
                      onChangeText={(v) => updateManualForm({ expiresAt: v })}
                    />
                  </Field>
                </View>
              </View>
              <View>
                <Text className="mb-2 text-xs text-neutral-500">분류</Text>
                <View className="flex-row flex-wrap gap-1.5">
                  {categoryOptions.map((c) => (
                    <Chip key={c} label={c} active={manualForm.category === c} onPress={() => updateManualForm({ category: c })} />
                  ))}
                </View>
              </View>
              <View>
                <Text className="mb-2 text-xs text-neutral-500">보관 위치</Text>
                <View className="flex-row gap-1.5">
                  {locationOptions.map((l) => (
                    <Chip key={l} label={l} active={manualForm.location === l} onPress={() => updateManualForm({ location: l })} />
                  ))}
                </View>
              </View>
              <Text className="text-xs text-accent-700">
                {previewDday ? `넣으면 ${previewDday}로 표시돼요` : '유통기한을 넣으면 D-day가 계산돼요'}
              </Text>
            </View>
            <Pressable
              onPress={() => closeAfter(submitManualAdd())}
              className="mt-4 rounded-full bg-accent-600 py-4 shadow-sm">
              <Text className="text-center text-[17px] font-bold text-white">냉장고에 넣기</Text>
            </Pressable>
          </>
        ) : null}

        {addMode === 'photo' ? (
          <View>
            <View className="h-[180px] items-center justify-center gap-2 rounded-[22px] bg-white px-6 shadow-sm">
              <Text className="text-[16px] text-neutral-900">
                {scanned ? '3가지를 찾았어요' : '사진을 찍어 주세요'}
              </Text>
              <Text className="text-center text-xs leading-5 text-neutral-500">
                영수증이나 냉장고 안을 찍으면{'\n'}재료와 유통기한을 대신 적어드려요
              </Text>
            </View>
            <Pressable onPress={startScan} className="mt-3.5 rounded-full bg-neutral-200 py-3.5">
              <Text className="text-center text-[14.5px] text-neutral-900">
                {scanned ? '다시 찍기' : '촬영하기'}
              </Text>
            </Pressable>

            {scanned ? (
              <View className="mt-5">
                <Text className="px-1 text-[13px] text-neutral-500">맞는지 확인해 주세요</Text>
                <View className="mt-2.5 gap-2">
                  {scanCandidates.map((c, i) => {
                    const picked = scanPicked.includes(i);
                    const icon = iconFor(c.name, c.category);
                    const dday = ddayLabel(decorateItem({ ...c, id: i }).dday);
                    return (
                      <Pressable
                        key={c.name}
                        onPress={() => toggleScanPick(i)}
                        className={`flex-row items-center gap-3 rounded-2xl px-3.5 py-3.5 shadow-sm ${
                          picked ? 'bg-white' : 'bg-white/60'
                        }`}>
                        <View
                          className={`h-5 w-5 items-center justify-center rounded-full border-[1.5px] ${
                            picked ? 'border-accent-600 bg-accent-600' : 'border-neutral-400 bg-transparent'
                          }`}>
                          {picked ? <Text className="text-[11px] text-white">✓</Text> : null}
                        </View>
                        <IconAvatar emoji={icon.emoji} bgClass={icon.bgClass} size={34} fontSize={17} />
                        <Text className="flex-1 text-[16px] text-neutral-900">{c.name}</Text>
                        <Text className="text-xs text-neutral-500">{c.quantity}</Text>
                        <View className="rounded-full bg-neutral-200 px-2.5 py-1.5">
                          <Text className="text-[11.5px] text-neutral-800">{dday}</Text>
                        </View>
                      </Pressable>
                    );
                  })}
                </View>
                <Pressable
                  onPress={() => closeAfter(submitScanAdd())}
                  className="mt-4 rounded-full bg-accent-600 py-4 shadow-sm">
                  <Text className="text-center text-[17px] font-bold text-white">
                    {scanPicked.length}가지 넣기
                  </Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        ) : null}

        {addMode === 'quick' ? (
          <View>
            <Text className="px-1 text-[13px] leading-5 text-neutral-500">
              자주 넣는 재료예요. 누르면 기본 수량과 보관 기간이 함께 들어가요.
            </Text>
            <View className="mt-4 flex-row flex-wrap gap-2">
              {quickAddNames.map((name) => {
                const active = quickPicked.includes(name);
                const tone = chipTone(active);
                const icon = iconFor(name, '');
                return (
                  <Pressable
                    key={name}
                    onPress={() => toggleQuickPick(name)}
                    className={`rounded-full px-3.5 py-2.5 ${tone.containerClass}`}>
                    <Text className={`text-[14.5px] ${tone.textClass}`}>
                      {icon.emoji} {name}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <Pressable
              onPress={() => closeAfter(submitQuickAdd())}
              className="mt-6 rounded-full bg-accent-600 py-4 shadow-sm">
              <Text className="text-center text-[17px] font-bold text-white">
                {quickPicked.length === 0 ? '재료를 골라주세요' : `${quickPicked.length}가지 넣기`}
              </Text>
            </Pressable>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <View>
      <Text className="mb-2 text-xs text-neutral-500">{label}</Text>
      {children}
    </View>
  );
}

