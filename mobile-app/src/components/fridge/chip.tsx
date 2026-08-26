import { Pressable, Text } from 'react-native';

import { chipTone } from '@/utils/fridge-logic';

export function Chip({
  label,
  active,
  onPress,
  size = 'md',
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  size?: 'sm' | 'md';
}) {
  const tone = chipTone(active);
  const padding = size === 'sm' ? 'px-3 py-1.5' : 'px-3.5 py-2';
  return (
    <Pressable
      onPress={onPress}
      className={`rounded-full ${padding} ${tone.containerClass}`}>
      <Text className={`text-[13px] ${tone.textClass}`}>{label}</Text>
    </Pressable>
  );
}
