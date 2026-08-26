import AsyncStorage from '@react-native-async-storage/async-storage';

const BASE_URL_KEY = 'fridge:apiBaseUrl';
const TOKEN_KEY = 'fridge:apiToken';

export type ApiConfig = {
  baseUrl: string;
  token: string;
};

function normalizeBaseUrl(url: string): string {
  return url.trim().replace(/\/+$/, '');
}

// 통합 데모용 기본값 — 설정 탭에서 아직 아무것도 저장한 적 없을 때만 쓰인다.
// EXPO_PUBLIC_* 환경변수는 빌드 타임에 인라인되는 Expo 표준 방식(하드코딩 아님).
const DEFAULT_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? '';
const DEFAULT_TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';

export async function getApiConfig(): Promise<ApiConfig | null> {
  const [baseUrl, token] = await Promise.all([
    AsyncStorage.getItem(BASE_URL_KEY),
    AsyncStorage.getItem(TOKEN_KEY),
  ]);
  if (baseUrl && token) return { baseUrl, token };
  if (DEFAULT_BASE_URL && DEFAULT_TOKEN) return { baseUrl: DEFAULT_BASE_URL, token: DEFAULT_TOKEN };
  return null;
}

export async function setApiConfig(config: ApiConfig): Promise<void> {
  await Promise.all([
    AsyncStorage.setItem(BASE_URL_KEY, normalizeBaseUrl(config.baseUrl)),
    AsyncStorage.setItem(TOKEN_KEY, config.token.trim()),
  ]);
}

export async function clearApiConfig(): Promise<void> {
  await Promise.all([AsyncStorage.removeItem(BASE_URL_KEY), AsyncStorage.removeItem(TOKEN_KEY)]);
}
