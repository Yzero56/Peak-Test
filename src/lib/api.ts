import { getApiConfig } from '@/lib/api-config';
import type { ClimateReading, InventoryItem, RecipeDef, ScanCandidate } from '@/types/fridge';

/** 백엔드 설정이 없거나(미설정) 요청이 실패하면 던져진다 — 호출부는 이걸 잡아서 로컬 폴백을 쓴다. */
export class ApiUnavailableError extends Error {}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const config = await getApiConfig();
  if (!config) throw new ApiUnavailableError('백엔드가 설정되지 않았어요');

  let res: Response;
  try {
    res = await fetch(`${config.baseUrl}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-App-Token': config.token,
        ...options.headers,
      },
    });
  } catch (err) {
    throw new ApiUnavailableError(`백엔드에 연결하지 못했어요: ${String(err)}`);
  }

  if (!res.ok) {
    throw new ApiUnavailableError(`백엔드 요청 실패 (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function fetchInventory(): Promise<InventoryItem[]> {
  return apiFetch<InventoryItem[]>('/api/inventory');
}

export function createInventoryItems(items: Omit<InventoryItem, 'id'>[]): Promise<InventoryItem[]> {
  return apiFetch<InventoryItem[]>('/api/inventory', {
    method: 'POST',
    body: JSON.stringify(items),
  });
}

export function patchInventoryItem(id: number, patch: Partial<Pick<InventoryItem, 'quantity' | 'expiresAt'>>): Promise<InventoryItem> {
  return apiFetch<InventoryItem>(`/api/inventory/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

export function deleteInventoryItem(id: number): Promise<void> {
  return apiFetch<void>(`/api/inventory/${id}`, { method: 'DELETE' });
}

export function fetchScanCandidates(): Promise<ScanCandidate[]> {
  return apiFetch<ScanCandidate[]>('/api/scan-candidates');
}

export function fetchClimate(): Promise<ClimateReading> {
  return apiFetch<ClimateReading>('/api/climate');
}

export function fetchRecipes(): Promise<RecipeDef[]> {
  return apiFetch<RecipeDef[]>('/api/recipes');
}
