import { Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { FoodItemRow } from '@/components/dashboard/food-item-row';
import { NotificationItem } from '@/components/dashboard/notification-item';
import { RecipeCard } from '@/components/dashboard/recipe-card';
import { SectionHeader } from '@/components/dashboard/section-header';
import { SensorStatusCard } from '@/components/dashboard/sensor-status-card';
import { BottomTabInset, Spacing } from '@/constants/theme';
import {
  mockDoorStatus,
  mockFoodItems,
  mockGasStatus,
  mockNotifications,
  mockRecipes,
} from '@/data/mock-fridge-data';
import { getDday } from '@/utils/dday';

// 웹에서는 app-tabs.web.tsx의 플로팅 상단 내비게이션 바와 겹치지 않도록 여백을 더 둡니다.
const contentPadding = Platform.select({
  web: { paddingTop: Spacing.six + Spacing.three, paddingBottom: Spacing.four },
  default: { paddingTop: Spacing.two, paddingBottom: BottomTabInset + Spacing.three },
});

const todayLabel = new Date().toLocaleDateString('ko-KR', {
  month: 'long',
  day: 'numeric',
  weekday: 'short',
});

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

const gasLabel = { normal: '정상', caution: '주의', danger: '위험' } as const;
const gasTone = { normal: 'good', caution: 'warning', danger: 'danger' } as const;

export default function DashboardScreen() {
  const sortedFoodItems = [...mockFoodItems].sort(
    (a, b) => getDday(a.expiresAt) - getDday(b.expiresAt),
  );
  const unreadCount = mockNotifications.filter((n) => !n.read).length;

  return (
    <SafeAreaView className="flex-1 bg-white dark:bg-black" edges={['top']}>
      <ScrollView
        className="flex-1"
        contentContainerClassName="gap-6 px-4"
        contentContainerStyle={contentPadding}
        showsVerticalScrollIndicator={false}>
        <View className="flex-row items-center justify-between">
          <View>
            <Text className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">
              냉장고 지킴이
            </Text>
            <Text className="text-sm text-neutral-400 dark:text-neutral-500">{todayLabel}</Text>
          </View>
          <View className="h-10 w-10 items-center justify-center rounded-full bg-neutral-100 dark:bg-neutral-900">
            <Text className="text-lg">🔔</Text>
            {unreadCount > 0 ? (
              <View className="absolute -right-1 -top-1 h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1">
                <Text className="text-[10px] font-bold text-white">{unreadCount}</Text>
              </View>
            ) : null}
          </View>
        </View>

        <View className="flex-row gap-3">
          <SensorStatusCard
            icon="🚪"
            title="도어 센서"
            value={mockDoorStatus.isOpen ? '열림' : '닫힘'}
            subtext={`${formatTime(mockDoorStatus.lastChangedAt)}에 마지막 변경`}
            tone={mockDoorStatus.isOpen ? 'warning' : 'good'}
          />
          <SensorStatusCard
            icon="🌬️"
            title="가스 센서 (BME680)"
            value={`${gasLabel[mockGasStatus.level]} · ${mockGasStatus.ppm}ppm`}
            subtext={`${formatTime(mockGasStatus.lastUpdatedAt)} 업데이트`}
            tone={gasTone[mockGasStatus.level]}
          />
        </View>

        <View className="gap-3">
          <SectionHeader title="오늘의 추천 레시피" trailing="소비 우선순위 기반" />
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerClassName="gap-3 pr-2">
            {mockRecipes.map((recipe) => (
              <View key={recipe.id} className="w-72">
                <RecipeCard recipe={recipe} />
              </View>
            ))}
          </ScrollView>
        </View>

        <View className="gap-3">
          <SectionHeader title="식재료 유통기한" trailing={`총 ${sortedFoodItems.length}개`} />
          <View className="gap-2">
            {sortedFoodItems.map((item) => (
              <FoodItemRow key={item.id} item={item} />
            ))}
          </View>
        </View>

        <View className="gap-3">
          <SectionHeader title="알림" trailing={`새 알림 ${unreadCount}개`} />
          <View className="gap-2">
            {mockNotifications.map((notification) => (
              <NotificationItem key={notification.id} notification={notification} />
            ))}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
