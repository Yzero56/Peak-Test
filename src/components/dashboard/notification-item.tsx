import { Text, View } from 'react-native';

import type { NotificationDigest } from '@/types/fridge';

function formatRelativeDate(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const diff = Math.round(
    (new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() -
      new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()) /
      (1000 * 60 * 60 * 24),
  );
  if (diff === 0) return '오늘';
  if (diff === 1) return '어제';
  return `${diff}일 전`;
}

export function NotificationItem({ notification }: { notification: NotificationDigest }) {
  return (
    <View className="flex-row gap-3 rounded-2xl bg-neutral-100 p-3 dark:bg-neutral-900">
      <View
        className={`mt-1.5 h-2 w-2 rounded-full ${
          notification.read ? 'bg-neutral-300 dark:bg-neutral-700' : 'bg-blue-500'
        }`}
      />
      <View className="flex-1 gap-1">
        <Text className="text-sm text-neutral-800 dark:text-neutral-200">
          {notification.summary}
        </Text>
        <Text className="text-xs text-neutral-400 dark:text-neutral-500">
          {formatRelativeDate(notification.date)} 요약
        </Text>
      </View>
    </View>
  );
}
