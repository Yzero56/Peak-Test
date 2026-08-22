import { Pressable, Text, View } from 'react-native';

import type { CalendarDay } from '@/utils/fridge-logic';

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

export function MealCalendar({
  days,
  selectedDate,
  onSelect,
}: {
  days: CalendarDay[];
  selectedDate: string;
  onSelect: (date: string) => void;
}) {
  return (
    <View className="rounded-[22px] bg-white px-3.5 pb-2.5 pt-4 shadow-sm">
      <View className="mb-1 flex-row">
        {WEEKDAYS.map((w) => (
          <Text key={w} className="flex-1 text-center text-[11px] text-neutral-500">
            {w}
          </Text>
        ))}
      </View>
      <View className="flex-row flex-wrap">
        {days.map((day) => {
          const selected = day.date === selectedDate;
          const bgClass = day.date == null ? '' : selected ? 'bg-accent-600' : day.isToday ? 'bg-accent-100' : '';
          const textClass = day.date == null ? '' : selected ? 'text-white' : 'text-neutral-900';
          return (
            <Pressable
              key={day.key}
              disabled={day.date == null}
              onPress={() => day.date && onSelect(day.date)}
              style={{ width: `${100 / 7}%` }}
              className="items-center justify-center gap-1 py-1.5">
              <View className={`h-11 w-11 items-center justify-center rounded-2xl ${bgClass}`}>
                <Text className={`text-[13px] ${textClass}`}>{day.label}</Text>
              </View>
              <View className="h-1 flex-row gap-0.5">
                {Array.from({ length: Math.min(day.mealCount, 3) }).map((_, i) => (
                  <View key={i} className={`h-1 w-1 rounded-full ${selected ? 'bg-accent-100' : 'bg-accent-600'}`} />
                ))}
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
