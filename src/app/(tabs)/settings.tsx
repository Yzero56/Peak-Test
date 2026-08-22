import { Platform, Pressable, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Chip } from '@/components/fridge/chip';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { useFridge } from '@/state/fridge-store';
import type { NotificationLeadTime, NotificationToggles } from '@/types/fridge';
import { decorateItem } from '@/utils/fridge-logic';

const contentPadding = Platform.select({
  web: { paddingTop: Spacing.six + Spacing.three, paddingBottom: Spacing.four },
  default: { paddingTop: Spacing.two, paddingBottom: BottomTabInset + Spacing.three },
});

const todayLabel = new Date().toLocaleDateString('ko-KR', {
  month: 'long',
  day: 'numeric',
  weekday: 'short',
});

const LEAD_OPTIONS: NotificationLeadTime[] = ['1일 전', '3일 전', '7일 전'];
const LEAD_DAYS: Record<NotificationLeadTime, number> = { '1일 전': 1, '3일 전': 3, '7일 전': 7 };

const TOGGLE_META: { key: keyof NotificationToggles; label: string; desc: string }[] = [
  { key: 'urgent', label: '임박 재료 알림', desc: '설정한 시점에 D-day 재료를 모아서 알려드려요' },
  { key: 'low', label: '재고 소진 알림', desc: '자주 쓰는 재료가 다 떨어지면 알려드려요' },
  { key: 'digest', label: '주간 리포트', desc: '일요일마다 식단과 활용률을 정리해 드려요' },
  { key: 'plan', label: '식단 자동 기록', desc: '요리를 완료하면 식단에 저절로 쌓여요' },
];

export default function SettingsScreen() {
  const { items, meals, leadTime, setLeadTime, toggles, toggleSetting } = useFridge();

  const dueCount = items.map((i) => decorateItem(i)).filter((i) => i.dday <= LEAD_DAYS[leadTime]).length;

  return (
    <SafeAreaView className="flex-1 bg-surface" edges={['top']}>
      <View className="px-5 pt-2.5">
        <Text className="text-xs text-neutral-500">{todayLabel}</Text>
        <Text className="mt-1.5 text-[26px] font-bold text-neutral-900">알림 설정</Text>
      </View>
      <ScrollView
        className="flex-1"
        contentContainerStyle={{ ...contentPadding, paddingHorizontal: 20 }}
        showsVerticalScrollIndicator={false}>
        <View className="rounded-[22px] bg-white p-[18px] shadow-sm">
          <Text className="text-[15.5px] text-neutral-900">언제 알려드릴까요?</Text>
          <View className="mt-3 flex-row gap-1.5">
            {LEAD_OPTIONS.map((opt) => (
              <Chip key={opt} label={opt} active={leadTime === opt} onPress={() => setLeadTime(opt)} />
            ))}
          </View>
          <Text className="mt-3 text-xs leading-5 text-neutral-500">
            유통기한 {leadTime} 오전 9시에 알려드려요. 지금 설정이면 오늘 {dueCount}건이 와요.
          </Text>
        </View>

        <View className="mt-3 rounded-[22px] bg-white px-[18px] shadow-sm">
          {TOGGLE_META.map((t, i) => (
            <View
              key={t.key}
              className={`flex-row items-center gap-3.5 py-[15px] ${i > 0 ? 'border-t border-divider' : ''}`}>
              <View className="flex-1">
                <Text className="text-[15.5px] text-neutral-900">{t.label}</Text>
                <Text className="mt-1 text-xs leading-5 text-neutral-500">{t.desc}</Text>
              </View>
              <Pressable
                onPress={() => toggleSetting(t.key)}
                className={`h-[27px] w-[46px] justify-center rounded-full px-0.5 ${
                  toggles[t.key] ? 'bg-accent-600' : 'bg-neutral-300'
                }`}>
                <View
                  className="h-[21px] w-[21px] rounded-full bg-white shadow-sm"
                  style={{ marginLeft: toggles[t.key] ? 19 : 0 }}
                />
              </Pressable>
            </View>
          ))}
        </View>

        <View className="mt-3 rounded-[22px] bg-white px-[18px] shadow-sm">
          <View className="flex-row justify-between border-b border-divider py-[15px]">
            <Text className="text-[15px] text-neutral-900">냉장고 속 재료</Text>
            <Text className="text-[15px] text-neutral-500">{items.length}개</Text>
          </View>
          <View className="flex-row justify-between py-[15px]">
            <Text className="text-[15px] text-neutral-900">기록된 식단</Text>
            <Text className="text-[15px] text-neutral-500">{meals.length}끼</Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
