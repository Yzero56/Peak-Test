import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

import { initialInventory, initialMeals, scanCandidates } from '@/data/mock-fridge-data';
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
  InventoryViewMode,
  ToastState,
} from '@/types/fridge';
import { bumpQuantity, ingredientsToConsume, toDateKey } from '@/utils/fridge-logic';

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
  scanPicked: number[];
  quickPicked: string[];
  selectedDate: string;
  leadTime: NotificationLeadTime;
  toggles: NotificationToggles;

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

  const openSheet = useCallback((id: number) => setSheetItemId(id), []);
  const closeSheet = useCallback(() => setSheetItemId(null), []);

  const removeSheetItem = useCallback(() => {
    setSheetItemId((currentId) => {
      if (currentId == null) return currentId;
      setItems((prevItems) => {
        const target = prevItems.find((i) => i.id === currentId);
        if (!target) return prevItems;
        const snapshot = prevItems;
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
    setScanPicked([0, 1, 2]);
    setQuickPicked([]);
  }, []);

  const finishAdd = useCallback(
    (newcomers: Omit<InventoryItem, 'id'>[]) => {
      if (newcomers.length === 0) return;
      setNextId((prevId) => {
        let id = prevId;
        const added = newcomers.map((x) => ({ id: id++, ...x }));
        setItems((prev) => [...prev, ...added]);
        setToast({
          message:
            added.length === 1 ? `${added[0].name}을 넣었어요` : `${added.length}가지를 넣었어요`,
          actionLabel: '확인',
          onAction: () => {},
        });
        return id;
      });
    },
    [],
  );

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
    setScanPicked([0, 1, 2]);
  }, []);

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
  }, [scanPicked, finishAdd, resetAddFlow]);

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
        setItems((prev) =>
          prev.map((item) => (item.id === currentId ? { ...item, quantity: bumpQuantity(item.quantity, delta) } : item)),
        );
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
      scanPicked,
      quickPicked,
      selectedDate,
      leadTime,
      toggles,

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
    }),
    [
      items, meals, rescuedCount, sheetItemId, toast, recipeSort, inventoryView, addMode,
      manualForm, scanned, scanPicked, quickPicked, selectedDate, leadTime, toggles,
      openSheet, closeSheet, bumpSheetQtyImpl, removeSheetItem, updateManualForm, submitManualAdd,
      startScan, toggleScanPick, submitScanAdd, toggleQuickPick, submitQuickAdd, resetAddFlow,
      cookRecipe, toggleSetting, dismissToast, runToastAction,
    ],
  );

  return <FridgeContext.Provider value={value}>{children}</FridgeContext.Provider>;
}

export function useFridge(): FridgeContextValue {
  const ctx = useContext(FridgeContext);
  if (!ctx) throw new Error('useFridge must be used within FridgeProvider');
  return ctx;
}
