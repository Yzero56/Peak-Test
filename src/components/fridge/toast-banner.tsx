import { Pressable, Text, View } from 'react-native';

import { useFridge } from '@/state/fridge-store';

export function ToastBanner() {
  const { toast, runToastAction } = useFridge();
  if (!toast) return null;

  return (
    <View
      pointerEvents="box-none"
      className="absolute inset-x-4 bottom-6 z-50 items-center">
      <View className="w-full max-w-md flex-row items-center gap-3 rounded-[18px] bg-neutral-900 px-4 py-3.5 shadow-lg">
        <Text className="flex-1 text-[13.5px] leading-5 text-white">{toast.message}</Text>
        <Pressable onPress={runToastAction} hitSlop={8}>
          <Text className="text-[13.5px] text-accent-300">{toast.actionLabel}</Text>
        </Pressable>
      </View>
    </View>
  );
}
