import { Text, View } from 'react-native';

type Tone = 'good' | 'warning' | 'danger' | 'neutral';

const toneStyles: Record<Tone, { dot: string; text: string }> = {
  good: { dot: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' },
  warning: { dot: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-400' },
  danger: { dot: 'bg-red-500', text: 'text-red-600 dark:text-red-400' },
  neutral: { dot: 'bg-neutral-400', text: 'text-neutral-500 dark:text-neutral-400' },
};

export function SensorStatusCard({
  icon,
  title,
  value,
  subtext,
  tone,
}: {
  icon: string;
  title: string;
  value: string;
  subtext: string;
  tone: Tone;
}) {
  const styles = toneStyles[tone];
  return (
    <View className="flex-1 gap-2 rounded-2xl bg-neutral-100 p-4 dark:bg-neutral-900">
      <View className="flex-row items-center justify-between">
        <Text className="text-2xl">{icon}</Text>
        <View className={`h-2.5 w-2.5 rounded-full ${styles.dot}`} />
      </View>
      <Text className="text-sm text-neutral-500 dark:text-neutral-400">{title}</Text>
      <Text className={`text-lg font-semibold ${styles.text}`}>{value}</Text>
      <Text className="text-xs text-neutral-400 dark:text-neutral-500">{subtext}</Text>
    </View>
  );
}
