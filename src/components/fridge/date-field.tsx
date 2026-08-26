import DateTimePicker from '@react-native-community/datetimepicker';
import { useState } from 'react';
import { Platform, Pressable, Text, TextInput } from 'react-native';

import { toDateKey } from '@/utils/fridge-logic';

/** 유통기한 입력 — 네이티브(iOS/Android)에서는 달력 피커, 웹에서는 텍스트 입력으로 대체. */
export function DateField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);

  if (Platform.OS === 'web') {
    return (
      <TextInput
        className="min-h-[44px] rounded-xl bg-neutral-100 px-3 text-[15px] text-neutral-900"
        placeholder="YYYY-MM-DD"
        placeholderTextColor="#a8adaa"
        value={value}
        onChangeText={onChange}
      />
    );
  }

  return (
    <>
      <Pressable
        onPress={() => setOpen(true)}
        className="min-h-[44px] justify-center rounded-xl bg-neutral-100 px-3">
        <Text className={`text-[15px] ${value ? 'text-neutral-900' : 'text-neutral-400'}`}>
          {value || 'YYYY-MM-DD'}
        </Text>
      </Pressable>
      {open ? (
        <DateTimePicker
          value={value ? new Date(value) : new Date()}
          mode="date"
          display="default"
          onChange={(event, selectedDate) => {
            setOpen(false);
            if (event.type === 'set' && selectedDate) {
              onChange(toDateKey(selectedDate));
            }
          }}
        />
      ) : null}
    </>
  );
}
