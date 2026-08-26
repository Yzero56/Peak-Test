import { StatusBar } from 'expo-status-bar';
import { DefaultTheme, ThemeProvider } from 'expo-router';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { View } from 'react-native';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import { ItemSheet } from '@/components/fridge/item-sheet';
import { ToastBanner } from '@/components/fridge/toast-banner';
import { FridgeProvider } from '@/state/fridge-store';

SplashScreen.preventAutoHideAsync();

// 이 앱은 v2 디자인의 Fresh 라이트 테마 하나만 지원합니다 — 시스템이 다크 모드여도 항상 라이트로 표시합니다.
export default function RootLayout() {
  return (
    <ThemeProvider value={DefaultTheme}>
      {/* 라이트 전용 앱이라 시스템이 다크 모드여도 상태바 아이콘은 항상 어두운 색(잘 보이는 쪽)으로 고정 */}
      <StatusBar style="dark" />
      <FridgeProvider>
        <View style={{ flex: 1 }}>
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="add" options={{ presentation: 'modal' }} />
          </Stack>
          <ToastBanner />
          <ItemSheet />
        </View>
      </FridgeProvider>
      <AnimatedSplashOverlay />
    </ThemeProvider>
  );
}
