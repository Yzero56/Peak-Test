import { useMemo } from 'react';
import { Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { MealCalendar } from '@/components/fridge/meal-calendar';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { useFridge } from '@/state/fridge-store';
import { buildMonthGrid, formatSelectedDateLabel } from '@/utils/fridge-logic';

const contentPadding = Platform.select({
  web: { paddingTop: Spacing.six + Spacing.three, paddingBottom: Spacing.four },
  default: { paddingTop: Spacing.two, paddingBottom: BottomTabInset + Spacing.three },
});

const today = new Date();

export default function MealsScreen() {
  const { meals, rescuedCount, selectedDate, setSelectedDate } = useFridge();

  const days = useMemo(
    () => buildMonthGrid(today.getFullYear(), today.getMonth(), meals, today),
    [meals],
  );
  const dayMeals = meals.filter((m) => m.date === selectedDate);
  const dayKcal = dayMeals.reduce((a, b) => a + b.kcal, 0);
  const totalKcal = meals.reduce((a, b) => a + b.kcal, 0);
  const avgKcal = meals.length > 0 ? Math.round(totalKcal / meals.length) : 0;

  return (
    <SafeAreaView className="flex-1 bg-surface" edges={['top']}>
      <View className="px-5 pt-2.5">
        <Text className="text-xs text-neutral-500">{today.getFullYear()}년</Text>
        <Text className="mt-1.5 text-[26px] font-bold text-neutral-900">
          {today.getMonth() + 1}월 식단
        </Text>
      </View>
      <ScrollView
        className="flex-1"
        contentContainerStyle={{ ...contentPadding, paddingHorizontal: 20 }}
        showsVerticalScrollIndicator={false}>
        <MealCalendar days={days} selectedDate={selectedDate} onSelect={setSelectedDate} />

        <View className="mt-3.5 flex-row gap-2.5">
          <Stat value={String(meals.length)} label="이번 달 요리" tone="accent" />
          <Stat value={String(avgKcal)} label="평균 kcal" />
          <Stat value={`${rescuedCount}개`} label="살린 재료" />
        </View>

        <View className="mt-6 flex-row items-baseline justify-between px-1">
          <Text className="text-[15px] text-neutral-900">{formatSelectedDateLabel(selectedDate)}</Text>
          <Text className="text-xs text-neutral-500">
            {dayMeals.length > 0 ? `${dayKcal}kcal · ${dayMeals.length}끼` : ''}
          </Text>
        </View>

        <View className="mt-2.5 gap-2">
          {dayMeals.map((m, i) => (
            <View key={i} className="flex-row items-center gap-2.5 rounded-2xl bg-white px-3.5 py-3.5 shadow-sm">
              <View className="rounded-full bg-accent-100 px-2.5 py-1.5">
                <Text className="text-[11.5px] text-accent-800">{m.slot}</Text>
              </View>
              <Text className="flex-1 text-[16px] text-neutral-900">{m.title}</Text>
              <Text className="text-xs text-neutral-500">{m.kcal}kcal</Text>
            </View>
          ))}
        </View>

        {dayMeals.length === 0 ? (
          <View className="mt-2.5 items-center rounded-2xl bg-white px-4 py-[22px] shadow-sm">
            <Text className="text-center text-[13.5px] leading-5 text-neutral-500">
              아직 기록이 없어요{'\n'}레시피를 완료하면 여기에 쌓여요
            </Text>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ value, label, tone }: { value: string; label: string; tone?: 'accent' }) {
  const bg = tone === 'accent' ? 'bg-accent-100' : 'bg-white';
  const valueColor = tone === 'accent' ? 'text-accent-800' : 'text-neutral-900';
  return (
    <View className={`flex-1 rounded-2xl px-3.5 py-3.5 ${bg}`}>
      <Text className={`text-[22px] font-bold leading-6 ${valueColor}`}>{value}</Text>
      <Text className="mt-1.5 text-[11.5px] text-neutral-600">{label}</Text>
    </View>
  );
}
