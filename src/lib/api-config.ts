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

export async function getApiConfig(): Promise<ApiConfig | null> {
  const [baseUrl, token] = await Promise.all([
    AsyncStorage.getItem(BASE_URL_KEY),
    AsyncStorage.getItem(TOKEN_KEY),
  ]);
  if (!baseUrl || !token) return null;
  return { baseUrl, token };
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
