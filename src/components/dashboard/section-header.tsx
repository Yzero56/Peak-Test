import { Text, View } from 'react-native';

export function SectionHeader({ title, trailing }: { title: string; trailing?: string }) {
  return (
    <View className="flex-row items-center justify-between">
      <Text className="text-lg font-semibold text-neutral-900 dark:text-neutral-50">{title}</Text>
      {trailing ? (
        <Text className="text-xs text-neutral-400 dark:text-neutral-500">{trailing}</Text>
      ) : null}
    </View>
  );
}
