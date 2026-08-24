import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import {
  createInventoryItems,
  deleteInventoryItem,
  fetchInventory,
  fetchScanCandidates,
  patchInventoryItem,
} from '@/lib/api';
import { getApiConfig } from '@/lib/api-config';
import { initialInventory, initialMeals, scanCandidates as mockScanCandidates } from '@/data/mock-fridge-data';
import type {
  AddMode,
  Category,
  InventoryItem,
  Location,
  ManualAddForm,
  MealLogEntry,
  NotificationLeadTime,
  NotificationToggles,
  RecipeDef,
  RecipeSortOrder,
  ScanCandidate,
  InventoryViewMode,
  ToastState,
} from '@/types/fridge';
import { bumpQuantity, ingredientsToConsume, toDateKey } from '@/utils/fridge-logic';

const BACKEND_POLL_MS = 6000;

function allIndices(count: number): number[] {
  return Array.from({ length: count }, (_, i) => i);
}

function defaultManualForm(): ManualAddForm {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  return {
    name: '',
    quantity: '',
    expiresAt: toDateKey(d),
    category: '채소',
    location: '냉장',
  };
}

type FridgeContextValue = {
  items: InventoryItem[];
  meals: MealLogEntry[];
  rescuedCount: number;
  sheetItemId: number | null;
  toast: ToastState | null;
  recipeSort: RecipeSortOrder;
  inventoryView: InventoryViewMode;
  addMode: AddMode;
  manualForm: ManualAddForm;
  scanned: boolean;
  scanCandidates: ScanCandidate[];
  scanPicked: number[];
  quickPicked: string[];
  selectedDate: string;
  leadTime: NotificationLeadTime;
  toggles: NotificationToggles;
  backendConnected: boolean;

  setInventoryView: (v: InventoryViewMode) => void;
  setRecipeSort: (v: RecipeSortOrder) => void;
  openSheet: (id: number) => void;
  closeSheet: () => void;
  bumpSheetQty: (delta: number) => void;
  removeSheetItem: () => void;

  setAddMode: (m: AddMode) => void;
  updateManualForm: (patch: Partial<ManualAddForm>) => void;
  submitManualAdd: () => boolean;
  startScan: () => void;
  toggleScanPick: (index: number) => void;
  submitScanAdd: () => boolean;
  toggleQuickPick: (name: string) => void;
  submitQuickAdd: () => boolean;
  resetAddFlow: () => void;

  cookRecipe: (recipe: RecipeDef) => void;
  setSelectedDate: (date: string) => void;

  setLeadTime: (lead: NotificationLeadTime) => void;
  toggleSetting: (key: keyof NotificationToggles) => void;

  dismissToast: () => void;
  runToastAction: () => void;

  /** 설정 화면에서 백엔드 주소/토큰을 저장한 뒤 호출 — 즉시 재고를 다시 불러온다. */
  reloadFromBackend: () => Promise<boolean>;
};

const FridgeContext = createContext<FridgeContextValue | null>(null);

export function FridgeProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<InventoryItem[]>(initialInventory);
  const [meals, setMeals] = useState<MealLogEntry[]>(initialMeals);
  const [rescuedCount, setRescuedCount] = useState(9);
  const [nextId, setNextId] = useState(100);
  const [sheetItemId, setSheetItemId] = useState<number | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [recipeSort, setRecipeSort] = useState<RecipeSortOrder>('match');
  const [inventoryView, setInventoryView] = useState<InventoryViewMode>('exp');
  const [addMode, setAddMode] = useState<AddMode>('manual');
  const [manualForm, setManualForm] = useState<ManualAddForm>(defaultManualForm);
  const [scanned, setScanned] = useState(false);
  const [scanCandidates, setScanCandidates] = useState<ScanCandidate[]>(mockScanCandidates);
  const [scanPicked, setScanPicked] = useState<number[]>([0, 1, 2]);
  const [quickPicked, setQuickPicked] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>(() => toDateKey(new Date()));
  const [leadTime, setLeadTime] = useState<NotificationLeadTime>('3일 전');
  const [toggles, setToggles] = useState<NotificationToggles>({
    urgent: true,
    low: true,
    digest: false,
    plan: true,
  });
  const [backendConnected, setBackendConnected] = useState(false);
  // 백엔드가 설정돼있는지는 폴링/뮤테이션 경로에서 매번 확인하지 않고 ref로 캐싱한다.
  const backendConfigured = useRef(false);

  const loadFromBackend = useCallback(async (): Promise<boolean> => {
    const config = await getApiConfig();
    backendConfigured.current = config != null;
    if (!config) {
      setBackendConnected(false);
      return false;
    }
    try {
      const remoteItems = await fetchInventory();
      setItems(remoteItems);
      setBackendConnected(true);
      return true;
    } catch {
      // 실패하면 화면에 이미 떠 있는 데이터(로컬 목업이든 이전 서버 응답이든)를 그대로 둔다.
      setBackendConnected(false);
      return false;
    }
  }, []);

  useEffect(() => {
    loadFromBackend();
    const interval = setInterval(loadFromBackend, BACKEND_POLL_MS);
    return () => clearInterval(interval);
  }, [loadFromBackend]);

  const openSheet = useCallback((id: number) => setSheetItemId(id), []);
  const closeSheet = useCallback(() => setSheetItemId(null), []);

  const removeSheetItem = useCallback(() => {
    setSheetItemId((currentId) => {
      if (currentId == null) return currentId;
      setItems((prevItems) => {
        const target = prevItems.find((i) => i.id === currentId);
        if (!target) return prevItems;
        const snapshot = prevItems;
        if (backendConfigured.current) {
          deleteInventoryItem(currentId).catch(() => setItems(snapshot));
        }
        setToast({
          message: `${target.name}을 비웠어요`,
          actionLabel: '되돌리기',
          onAction: () => setItems(snapshot),
        });
        return prevItems.filter((i) => i.id !== currentId);
      });
      return null;
    });
  }, []);

  const updateManualForm = useCallback((patch: Partial<ManualAddForm>) => {
    setManualForm((prev) => ({ ...prev, ...patch }));
  }, []);

  const resetAddFlow = useCallback(() => {
    setAddMode('manual');
    setManualForm(defaultManualForm());
    setScanned(false);
    setScanPicked([]);
    setQuickPicked([]);
  }, []);

  const finishAdd = useCallback((newcomers: Omit<InventoryItem, 'id'>[]) => {
    if (newcomers.length === 0) return;

    if (backendConfigured.current) {
      createInventoryItems(newcomers)
        .then((created) => {
          setItems((prev) => [...prev, ...created]);
          setToast({
            message:
              created.length === 1 ? `${created[0].name}을 넣었어요` : `${created.length}가지를 넣었어요`,
            actionLabel: '확인',
            onAction: () => {},
          });
        })
        .catch(() => {
          setToast({ message: '백엔드에 저장하지 못했어요', actionLabel: '확인', onAction: () => {} });
        });
      return;
    }

    setNextId((prevId) => {
      let id = prevId;
      const added = newcomers.map((x) => ({ id: id++, ...x }));
      setItems((prev) => [...prev, ...added]);
      setToast({
        message: added.length === 1 ? `${added[0].name}을 넣었어요` : `${added.length}가지를 넣었어요`,
        actionLabel: '확인',
        onAction: () => {},
      });
      return id;
    });
  }, []);

  const submitManualAdd = useCallback((): boolean => {
    if (!manualForm.name.trim()) {
      setToast({ message: '재료 이름을 알려주세요', actionLabel: '확인', onAction: () => {} });
      return false;
    }
    finishAdd([
      {
        name: manualForm.name.trim(),
        quantity: manualForm.quantity || '1개',
        expiresAt: manualForm.expiresAt,
        category: manualForm.category,
        location: manualForm.location,
      },
    ]);
    resetAddFlow();
    return true;
  }, [manualForm, finishAdd, resetAddFlow]);

  const startScan = useCallback(() => {
    setScanned(true);
    // 백엔드 미설정/실패 시엔 직전 후보 개수를 그대로 기준으로 삼는다(아래 fetch 성공 시 다시 맞춤).
    setScanPicked(allIndices(scanCandidates.length));
    if (backendConfigured.current) {
      fetchScanCandidates()
        .then((candidates) => {
          setScanCandidates(candidates);
          setScanPicked(allIndices(candidates.length));
        })
        .catch(() => {
          // 실패하면 마지막으로 알던 후보(직전 서버 응답 또는 목업)를 그대로 둔다.
        });
    }
  }, [scanCandidates.length]);

  const toggleScanPick = useCallback((index: number) => {
    setScanPicked((prev) => (prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]));
  }, []);

  const submitScanAdd = useCallback((): boolean => {
    if (scanPicked.length === 0) return false;
    finishAdd(
      scanPicked.map((i) => {
        const c = scanCandidates[i];
        return { name: c.name, quantity: c.quantity, expiresAt: c.expiresAt, category: c.category, location: c.location };
      }),
    );
    resetAddFlow();
    return true;
  }, [scanPicked, scanCandidates, finishAdd, resetAddFlow]);

  const toggleQuickPick = useCallback((name: string) => {
    setQuickPicked((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]));
  }, []);

  const submitQuickAdd = useCallback((): boolean => {
    if (quickPicked.length === 0) return false;
    const exp = defaultManualForm().expiresAt;
    finishAdd(quickPicked.map((name) => ({ name, quantity: '1개', expiresAt: exp, category: '기타' as Category, location: '냉장' as Location })));
    resetAddFlow();
    return true;
  }, [quickPicked, finishAdd, resetAddFlow]);

  const cookRecipe = useCallback(
    (recipe: RecipeDef) => {
      setItems((prevItems) => {
        const drop = ingredientsToConsume(recipe, prevItems);
        const snapshotItems = prevItems;
        const today = toDateKey(new Date());

        if (backendConfigured.current) {
          const droppedIds = prevItems.filter((i) => drop.includes(i.name)).map((i) => i.id);
          for (const id of droppedIds) {
            deleteInventoryItem(id).catch(() => {});
          }
        }

        setMeals((prevMeals) => {
          const snapshotMeals = prevMeals;
          setRescuedCount((prevRescued) => {
            const snapshotRescued = prevRescued;
            setToast({
              message: `재료 ${drop.length}개를 정리하고 저녁 식단에 기록했어요`,
              actionLabel: '되돌리기',
              onAction: () => {
                setItems(snapshotItems);
                setMeals(snapshotMeals);
                setRescuedCount(snapshotRescued);
              },
            });
            return prevRescued + drop.length;
          });
          return [...prevMeals, { date: today, slot: '저녁', title: recipe.title, kcal: recipe.kcal }];
        });
        return prevItems.filter((i) => !drop.includes(i.name));
      });
    },
    [],
  );

  const toggleSetting = useCallback((key: keyof NotificationToggles) => {
    setToggles((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const dismissToast = useCallback(() => setToast(null), []);
  const runToastAction = useCallback(() => {
    setToast((current) => {
      current?.onAction();
      return null;
    });
  }, []);

  // sheet 수량 조절은 sheetItemId를 함께 참조해야 하므로 여기서 재정의한다.
  const bumpSheetQtyImpl = useCallback(
    (delta: number) => {
      setSheetItemId((currentId) => {
        if (currentId == null) return currentId;
        setItems((prev) => {
          const next = prev.map((item) =>
            item.id === currentId ? { ...item, quantity: bumpQuantity(item.quantity, delta) } : item,
          );
          if (backendConfigured.current) {
            const updated = next.find((i) => i.id === currentId);
            if (updated) {
              patchInventoryItem(currentId, { quantity: updated.quantity }).catch(() => setItems(prev));
            }
          }
          return next;
        });
        return currentId;
      });
    },
    [],
  );

  const value = useMemo<FridgeContextValue>(
    () => ({
      items,
      meals,
      rescuedCount,
      sheetItemId,
      toast,
      recipeSort,
      inventoryView,
      addMode,
      manualForm,
      scanned,
      scanCandidates,
      scanPicked,
      quickPicked,
      selectedDate,
      leadTime,
      toggles,
      backendConnected,

      setInventoryView,
      setRecipeSort,
      openSheet,
      closeSheet,
      bumpSheetQty: bumpSheetQtyImpl,
      removeSheetItem,

      setAddMode,
      updateManualForm,
      submitManualAdd,
      startScan,
      toggleScanPick,
      submitScanAdd,
      toggleQuickPick,
      submitQuickAdd,
      resetAddFlow,

      cookRecipe,
      setSelectedDate,

      setLeadTime,
      toggleSetting,

      dismissToast,
      runToastAction,

      reloadFromBackend: loadFromBackend,
    }),
    [
      items, meals, rescuedCount, sheetItemId, toast, recipeSort, inventoryView, addMode,
      manualForm, scanned, scanCandidates, scanPicked, quickPicked, selectedDate, leadTime, toggles,
      backendConnected, openSheet, closeSheet, bumpSheetQtyImpl, removeSheetItem, updateManualForm, submitManualAdd,
      startScan, toggleScanPick, submitScanAdd, toggleQuickPick, submitQuickAdd, resetAddFlow,
      cookRecipe, toggleSetting, dismissToast, runToastAction, loadFromBackend,
    ],
  );

  return <FridgeContext.Provider value={value}>{children}</FridgeContext.Provider>;
}

export function useFridge(): FridgeContextValue {
  const ctx = useContext(FridgeContext);
  if (!ctx) throw new Error('useFridge must be used within FridgeProvider');
  return ctx;
}
