"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ChevronDown, ChevronUp, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormDescription,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";

const typeOptions = [
  { value: "ASSET", label: "資產" },
  { value: "LIABILITY", label: "負債" },
];

const categoryOptions = [
  { value: "CASH", label: "現金" },
  { value: "BANK_ACCOUNT", label: "銀行帳戶" },
  { value: "TAIWAN_STOCK", label: "台股" },
  { value: "US_STOCK", label: "美股" },
  { value: "CRYPTO", label: "虛擬貨幣" },
  { value: "FIXED_ASSET", label: "固定資產" },
  { value: "RECEIVABLE", label: "應收款" },
  { value: "PAYABLE", label: "應付款" },
  { value: "MORTGAGE", label: "房貸" },
  { value: "CAR_LOAN", label: "車貸" },
  { value: "CREDIT_LOAN", label: "信用貸款" },
];

const currencyOptions = [
  { value: "TWD", label: "TWD" },
  { value: "USD", label: "USD" },
];

const categoryLabelMap: Record<string, string> = {
  CASH: "現金",
  BANK_ACCOUNT: "銀行帳戶",
  TAIWAN_STOCK: "台股",
  US_STOCK: "美股",
  CRYPTO: "虛擬貨幣",
  FIXED_ASSET: "固定資產",
  RECEIVABLE: "應收款",
  PAYABLE: "應付款",
  MORTGAGE: "房貸",
  CAR_LOAN: "車貸",
  CREDIT_LOAN: "信用貸款",
};

const symbolRequiredCategories = ["TAIWAN_STOCK", "US_STOCK", "CRYPTO"];
const amountInputCategories = [
  "CASH",
  "BANK_ACCOUNT",
  "FIXED_ASSET",
  "RECEIVABLE",
  "PAYABLE",
  "MORTGAGE",
  "CAR_LOAN",
  "CREDIT_LOAN",
];

type Account = {
  id: string;
  name: string;
  type: string;
  category: string;
  symbol: string | null;
  quantity: number | null;
  currency: string;
  isApiConnected: boolean;
  apiSource: string | null;
  apiKey: string | null;
  apiSecret: string | null;
  currentPrice: number | null;
  currentValue: number;
  monthlyDeductionAmount: number | null;
  deductionDate: number | null;
  createdAt: string;
};

type HistoryPoint = {
  id: string;
  date: string;
  totalAssets: number;
  totalLiabilities: number;
  netWorth: number;
};

type TransactionRecord = {
  id: string;
  accountId: string;
  type: string;
  amount: number;
  description: string | null;
  date: string;
  account: {
    name: string;
  } | null;
};

const defaultForm = {
  name: "",
  type: "ASSET",
  category: "CASH",
  symbol: "",
  quantity: "0",
  currency: "TWD",
  isApiConnected: false,
  apiSource: "BITFINEX",
  apiKey: "",
  apiSecret: "",
  monthlyDeductionAmount: "",
  deductionDate: "",
};

export default function HomePage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [formData, setFormData] = useState(defaultForm);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [transactions, setTransactions] = useState<TransactionRecord[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editingAccountId, setEditingAccountId] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<"day" | "month" | "quarter" | "year">("day");
  const [mounted, setMounted] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  const isCryptoApiMode = formData.category === "CRYPTO" && formData.isApiConnected;
  const requiresSymbol = symbolRequiredCategories.includes(formData.category) && !isCryptoApiMode;
  const usesAmountInput = amountInputCategories.includes(formData.category);
  const showDeductionFields = formData.type === "LIABILITY";
  const showApiFields = formData.category === "CRYPTO" && formData.isApiConnected;

  const summary = useMemo(() => {
    const totalAssets = accounts
      .filter((account) => account.type === "ASSET")
      .reduce((sum, account) => sum + Number(account.currentValue ?? 0), 0);

    const totalLiabilities = accounts
      .filter((account) => account.type === "LIABILITY")
      .reduce((sum, account) => sum + Number(account.currentValue ?? 0), 0);

    return {
      totalAssets,
      totalLiabilities,
      netWorth: totalAssets - totalLiabilities,
    };
  }, [accounts]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    void (async () => {
      await Promise.allSettled([fetchAccounts(), fetchHistory(), fetchTransactions()]);
    })();
  }, []);

  async function fetchAccounts() {
    setError(null);
    try {
      const response = await fetch("/api/accounts");
      if (!response.ok) {
        throw new Error("無法取得帳戶清單。");
      }
      const data = (await response.json()) as Account[];
      setAccounts(data);
    } catch (fetchError) {
      setError(
        fetchError instanceof Error ? fetchError.message : "載入帳戶資料時發生錯誤。"
      );
    }
  }

  async function fetchHistory() {
    try {
      const response = await fetch("/api/history");
      if (!response.ok) {
        throw new Error("無法取得歷史資料。");
      }
      const data = (await response.json()) as HistoryPoint[];
      setHistory(data);
    } catch (historyError) {
      console.error("History request failed:", historyError);
    }
  }

  async function fetchTransactions() {
    try {
      const response = await fetch("/api/transactions");
      if (!response.ok) {
        throw new Error("無法取得交易紀錄。");
      }
      const data = (await response.json()) as TransactionRecord[];
      setTransactions(data);
    } catch (transactionError) {
      console.error("Transactions request failed:", transactionError);
    }
  }

  function resetForm() {
    setFormData(defaultForm);
    setEditingAccountId(null);
    setShowForm(false);
  }

  function startEdit(account: Account) {
    setFormData({
      name: account.name,
      type: account.type,
      category: account.category,
      symbol: account.symbol ?? "",
      quantity: String(account.quantity ?? account.currentValue ?? 0),
      currency: account.currency,
      isApiConnected: Boolean(account.isApiConnected),
      apiSource: account.apiSource ?? "BITFINEX",
      apiKey: account.apiKey ?? "",
      apiSecret: account.apiSecret ?? "",
      monthlyDeductionAmount: account.monthlyDeductionAmount != null ? String(account.monthlyDeductionAmount) : "",
      deductionDate: account.deductionDate != null ? String(account.deductionDate) : "",
    });
    setEditingAccountId(account.id);
    setShowForm(true);
    setError(null);
    setMessage(null);
    setSyncMessage(null);
  }

  function toggleGroup(groupTitle: string) {
    setCollapsedGroups((prev) => ({
      ...prev,
      [groupTitle]: !prev[groupTitle],
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setSyncMessage(null);

    if (!formData.name.trim()) {
      setError("請填寫名稱。");
      return;
    }

    if (!formData.type) {
      setError("請選擇類型。");
      return;
    }

    if (!formData.category) {
      setError("請選擇類別。");
      return;
    }

    if (requiresSymbol && !formData.symbol.trim()) {
      setError("股票或虛擬貨幣類別需要填寫代號。");
      return;
    }

    if (isCryptoApiMode) {
      if (!formData.apiKey.trim()) {
        setError("請填寫 API Key。");
        return;
      }

      if (!formData.apiSecret.trim()) {
        setError("請填寫 API Secret。");
        return;
      }
    }

    const parsedQuantity = isCryptoApiMode ? 0 : Number(formData.quantity ?? 0);
    if (!isCryptoApiMode && Number.isNaN(parsedQuantity)) {
      setError("數量/餘額必須是有效數字。");
      return;
    }

    const payload = {
      name: formData.name.trim(),
      type: formData.type,
      category: formData.category,
      symbol: isCryptoApiMode ? (formData.symbol.trim() || formData.apiSource || "BITFINEX") : (formData.symbol.trim() || null),
      quantity: parsedQuantity,
      currency: formData.currency,
      isApiConnected: isCryptoApiMode,
      apiSource: isCryptoApiMode ? (formData.apiSource || "BITFINEX") : null,
      apiKey: isCryptoApiMode ? formData.apiKey.trim() : null,
      apiSecret: isCryptoApiMode ? formData.apiSecret.trim() : null,
      monthlyDeductionAmount: showDeductionFields ? Number(formData.monthlyDeductionAmount || 0) : null,
      deductionDate: showDeductionFields ? Number(formData.deductionDate || 0) : null,
    };

    setLoading(true);
    try {
      const response = await fetch(editingAccountId ? `/api/accounts/${editingAccountId}` : "/api/accounts", {
        method: editingAccountId ? "PUT" : "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const result = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(result?.message || "儲存失敗。");
      }

      setMessage(editingAccountId ? "已成功更新帳戶。" : "已成功新增資產/負債。");
      resetForm();
      await Promise.allSettled([fetchAccounts(), fetchHistory(), fetchTransactions()]);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "儲存帳戶時發生錯誤。");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(accountId: string) {
    const confirmed = window.confirm("確定要刪除此項目嗎？");
    if (!confirmed) {
      return;
    }

    try {
      const response = await fetch(`/api/accounts/${accountId}`, { method: "DELETE" });
      const result = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(result?.message || "刪除失敗。");
      }

      setMessage("已成功刪除帳戶。");
      if (editingAccountId === accountId) {
        resetForm();
      }
      await Promise.allSettled([fetchAccounts(), fetchHistory(), fetchTransactions()]);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "刪除帳戶時發生錯誤。");
    }
  }

  async function handleSyncPrices() {
    setSyncing(true);
    setError(null);
    setMessage(null);
    setSyncMessage(null);

    try {
      const response = await fetch("/api/test-fetch-prices");
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result?.message || "同步最新報價失敗。" );
      }

      await Promise.allSettled([fetchAccounts(), fetchHistory(), fetchTransactions()]);
      const updatedCount = result?.databaseUpdate?.updates?.length ?? 0;
      setSyncMessage(`已同步最新報價，成功更新 ${updatedCount} 類型的帳戶價格。` );
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : "同步最新報價時發生錯誤。" );
    } finally {
      setSyncing(false);
    }
  }

  function formatCurrency(value: number) {
    return value.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
  }

  function formatPercent(value: number) {
    return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
  }

  function getTaipeiParts(date: Date) {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Taipei",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).formatToParts(date);

    return {
      year: Number(parts.find((part) => part.type === "year")?.value ?? "0"),
      month: Number(parts.find((part) => part.type === "month")?.value ?? "1"),
      day: Number(parts.find((part) => part.type === "day")?.value ?? "1"),
    };
  }

  function getTaipeiDateKey(date: Date) {
    return date.toLocaleDateString("zh-TW", {
      timeZone: "Asia/Taipei",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  }

  function getTaipeiTimeframeLabel(date: Date, selectedTimeframe: typeof timeframe) {
    if (selectedTimeframe === "day") {
      return date.toLocaleDateString("zh-TW", {
        timeZone: "Asia/Taipei",
        month: "numeric",
        day: "numeric",
      });
    }

    if (selectedTimeframe === "month") {
      const parts = getTaipeiParts(date);
      return `${parts.year} / ${String(parts.month).padStart(2, "0")}`;
    }

    if (selectedTimeframe === "quarter") {
      const parts = getTaipeiParts(date);
      const quarter = Math.floor((parts.month - 1) / 3) + 1;
      return `${parts.year}-Q${quarter}`;
    }

    const parts = getTaipeiParts(date);
    return `${parts.year} 年`;
  }

  function getTaipeiDayReference(offsetDays: number) {
    const now = new Date();
    const todayParts = getTaipeiParts(now);
    const taipeiMidnightUtc = new Date(Date.UTC(todayParts.year, todayParts.month - 1, todayParts.day, 0, 0, 0));
    taipeiMidnightUtc.setUTCDate(taipeiMidnightUtc.getUTCDate() + offsetDays);
    return taipeiMidnightUtc;
  }

  function buildFallbackHistory(currentNetWorth: number, selectedTimeframe: typeof timeframe) {
    const base = Math.max(1000, Number(currentNetWorth || 10000));
    const dailyDrop = Math.max(1000, Math.min(2000, base * 0.0008));

    if (selectedTimeframe === "day") {
      return Array.from({ length: 7 }, (_, index) => {
        const date = getTaipeiDayReference(index - 6);
        const value = index === 6 ? currentNetWorth : Math.max(1000, base - (6 - index) * dailyDrop);
        return {
          id: `fallback-day-${index}`,
          date: date.toISOString(),
          totalAssets: value,
          totalLiabilities: Math.max(0, value * 0.08),
          netWorth: value,
          label: getTaipeiTimeframeLabel(date, "day"),
        } as HistoryPoint;
      });
    }

    if (selectedTimeframe === "month") {
      return Array.from({ length: 6 }, (_, index) => {
        const current = getTaipeiDayReference(0);
        current.setUTCMonth(current.getUTCMonth() - (5 - index));
        const value = Math.max(1000, base - (5 - index) * dailyDrop * 5);
        return {
          id: `fallback-month-${index}`,
          date: current.toISOString(),
          totalAssets: value,
          totalLiabilities: Math.max(0, value * 0.08),
          netWorth: value,
          label: getTaipeiTimeframeLabel(current, "month"),
        } as HistoryPoint;
      });
    }

    if (selectedTimeframe === "quarter") {
      return Array.from({ length: 4 }, (_, index) => {
        const current = getTaipeiDayReference(0);
        current.setUTCMonth(current.getUTCMonth() - (3 - index) * 3);
        const value = Math.max(1000, base - (3 - index) * dailyDrop * 15);
        return {
          id: `fallback-quarter-${index}`,
          date: current.toISOString(),
          totalAssets: value,
          totalLiabilities: Math.max(0, value * 0.08),
          netWorth: value,
          label: getTaipeiTimeframeLabel(current, "quarter"),
        } as HistoryPoint;
      });
    }

    return Array.from({ length: 3 }, (_, index) => {
      const current = getTaipeiDayReference(0);
      current.setUTCFullYear(current.getUTCFullYear() - (2 - index));
      const value = Math.max(1000, base - (2 - index) * dailyDrop * 25);
      return {
        id: `fallback-year-${index}`,
        date: current.toISOString(),
        totalAssets: value,
        totalLiabilities: Math.max(0, value * 0.08),
        netWorth: value,
        label: getTaipeiTimeframeLabel(current, "year"),
      } as HistoryPoint;
    });
  }

  function buildChartSeries(historyPoints: HistoryPoint[], selectedTimeframe: typeof timeframe, currentNetWorth: number) {
    const sorted = [...historyPoints]
      .filter((point) => Number.isFinite(Number(point.netWorth)))
      .sort((left, right) => new Date(left.date).getTime() - new Date(right.date).getTime());

    const getKey = (date: Date, timeframeType: typeof timeframe) => {
      const parts = getTaipeiParts(date);
      if (timeframeType === "month") {
        return `${parts.year}-${String(parts.month).padStart(2, "0")}`;
      }
      if (timeframeType === "quarter") {
        const quarter = Math.floor((parts.month - 1) / 3) + 1;
        return `${parts.year}-Q${quarter}`;
      }
      if (timeframeType === "year") {
        return `${parts.year}`;
      }
      return getTaipeiDateKey(date);
    };

    const buildPoint = (date: Date, value: number, index: number) => ({
      id: `chart-${selectedTimeframe}-${index}`,
      date: date.toISOString(),
      totalAssets: value,
      totalLiabilities: Math.max(0, value * 0.08),
      netWorth: value,
      label: getTaipeiTimeframeLabel(date, selectedTimeframe),
    });

    if (selectedTimeframe === "day") {
      const today = getTaipeiDayReference(0);
      const dailyDrop = Math.max(1000, Math.min(2000, currentNetWorth * 0.0008 || 1000));
      const latestPointByDay = new Map<string, HistoryPoint>();

      for (const point of sorted) {
        const key = getTaipeiDateKey(new Date(point.date));
        const existing = latestPointByDay.get(key);
        if (!existing || new Date(point.date).getTime() > new Date(existing.date).getTime()) {
          latestPointByDay.set(key, point);
        }
      }

      return Array.from({ length: 7 }, (_, index) => {
        const date = getTaipeiDayReference(index - 6);
        const key = getTaipeiDateKey(date);
        if (index === 6) {
          return buildPoint(date, currentNetWorth, index);
        }

        const point = latestPointByDay.get(key);
        const value = point ? Number(point.netWorth ?? 0) : Math.max(1000, currentNetWorth - (6 - index) * dailyDrop);
        return buildPoint(date, value, index);
      });
    }

    if (sorted.length === 0) {
      return buildFallbackHistory(currentNetWorth, selectedTimeframe);
    }

    const grouped = new Map<string, HistoryPoint>();

    for (const point of sorted) {
      const key = getKey(new Date(point.date), selectedTimeframe);
      const existing = grouped.get(key);
      if (!existing || new Date(point.date).getTime() > new Date(existing.date).getTime()) {
        grouped.set(key, point);
      }
    }

    const maxLabels = selectedTimeframe === "month" ? 6 : selectedTimeframe === "quarter" ? 4 : 3;
    return Array.from(grouped.entries())
      .slice(-maxLabels)
      .map(([key, point]) => ({
        ...point,
        netWorth: Number(point.netWorth ?? 0),
        label: getTaipeiTimeframeLabel(new Date(point.date), selectedTimeframe),
      }));
  }

  const accountGroups = [
    { title: "【流動資金】", categories: ["BANK_ACCOUNT", "CASH"], accent: "from-emerald-500 to-teal-500" },
    { title: "【投資組合】", categories: ["TAIWAN_STOCK", "US_STOCK", "CRYPTO"], accent: "from-sky-500 to-blue-500" },
    { title: "【固定資產】", categories: ["FIXED_ASSET"], accent: "from-amber-500 to-orange-500" },
    { title: "【應收款項】", categories: ["RECEIVABLE"], accent: "from-violet-500 to-fuchsia-500" },
    { title: "【負債與應付款】", categories: ["PAYABLE", "MORTGAGE", "CAR_LOAN", "CREDIT_LOAN"], accent: "from-rose-500 to-pink-500" },
  ];

  const chartData = useMemo(() => buildChartSeries(history, timeframe, summary.netWorth), [history, timeframe, summary.netWorth]);

  const trendDelta = useMemo(() => {
    const yesterdayKey = getTaipeiDateKey(getTaipeiDayReference(-1));
    const yesterdayPoints = history
      .map((point) => ({
        point,
        key: getTaipeiDateKey(new Date(point.date)),
        timestamp: new Date(point.date).getTime(),
      }))
      .filter((item) => item.key === yesterdayKey)
      .sort((left, right) => left.timestamp - right.timestamp);

    const yesterdayPoint = yesterdayPoints.length ? yesterdayPoints[yesterdayPoints.length - 1].point : null;
    const yesterdayValue = Number(yesterdayPoint?.netWorth ?? 0);

    if (!yesterdayValue) {
      return 0;
    }

    return ((summary.netWorth - yesterdayValue) / yesterdayValue) * 100;
  }, [history, summary.netWorth]);

  const renderedAccountGroups = useMemo(() => {
    return accountGroups
      .map((group) => {
        const relevantAccounts = accounts.filter((account) => group.categories.includes(account.category));
        if (relevantAccounts.length === 0) {
          return null;
        }

        const isInvestmentGroup = group.categories.some((category) => symbolRequiredCategories.includes(category));

        const groupedCards = Object.values(
          relevantAccounts.reduce<Record<string, { id: string; title: string; subtitle: string; category: string; quantity: number; currentValue: number; accountCount: number; account: Account }>>(
            (result, account) => {
              if (isInvestmentGroup) {
                const symbol = (account.symbol || account.name || "").trim().toUpperCase();
                const accountName = account.name.trim();
                const key = `${symbol}::${accountName}`;

                if (!result[key]) {
                  result[key] = {
                    id: `investment-${key}`,
                    title: symbol,
                    subtitle: accountName,
                    category: account.category,
                    quantity: 0,
                    currentValue: 0,
                    accountCount: 0,
                    account,
                  };
                }

                result[key].quantity += Number(account.quantity ?? 0);
                result[key].currentValue += Number(account.currentValue ?? 0);
                result[key].accountCount += 1;
                return result;
              }

              const key = account.name.trim().toLowerCase();
              if (!result[key]) {
                result[key] = {
                  id: `group-${key}`,
                  title: account.name,
                  subtitle: categoryLabelMap[account.category] ?? account.category,
                  category: account.category,
                  quantity: 0,
                  currentValue: 0,
                  accountCount: 0,
                  account,
                };
              }

              result[key].quantity += Number(account.quantity ?? 0);
              result[key].currentValue += Number(account.currentValue ?? 0);
              result[key].accountCount += 1;
              if (result[key].accountCount > 1) {
                result[key].subtitle = `${categoryLabelMap[account.category] ?? account.category} · 多筆同名帳戶`;
              }
              return result;
            },
            {}
          )
        );

        return {
          ...group,
          cards: groupedCards,
        };
      })
      .filter(Boolean);
  }, [accounts]);

  useEffect(() => {
    setCollapsedGroups((prev) => {
      const next = { ...prev };
      renderedAccountGroups.forEach((group) => {
        if (!group) {
          return;
        }
        if (next[group.title] !== undefined) {
          return;
        }
        next[group.title] = group.cards.length > 2 || ["【固定資產】", "【負債與應付款】"].includes(group.title);
      });
      return next;
    });
  }, [renderedAccountGroups]);

  return (
    <>
      <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.12),_transparent_35%),linear-gradient(135deg,_#f8fafc_0%,_#f1f5f9_100%)] px-4 py-8 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <section className="rounded-[2rem] border border-slate-200/70 bg-white/80 p-6 shadow-[0_24px_80px_-32px_rgba(15,23,42,0.35)] backdrop-blur xl:p-8">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-center xl:justify-between">
            <div className="max-w-3xl">
              <p className="text-sm font-medium uppercase tracking-[0.3em] text-emerald-600">NetWorth Tracker</p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">
                財務一覽、趨勢清楚。
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
                將現金、投資、負債與淨資產集中成一張儀表板，讓財務決策更專注、視覺更直覺。
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleSyncPrices}
                disabled={syncing}
                className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-emerald-600 to-teal-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-emerald-500/10 transition hover:from-emerald-700 hover:to-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {syncing ? (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                    同步中...
                  </>
                ) : (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    同步最新報價
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(true)}
                className="inline-flex items-center justify-center rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
              >
                ＋ 新增項目
              </button>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[0.52fr_1fr]">
          <div className="rounded-[2rem] border border-slate-200/70 bg-white/90 p-6 shadow-[0_22px_50px_-24px_rgba(15,23,42,0.22)]">
            <div className="flex flex-col gap-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium uppercase tracking-[0.25em] text-slate-500">
                    目前淨資產
                  </p>
                  <p className="mt-3 text-4xl font-semibold text-slate-950">
                    NT$ {formatCurrency(summary.netWorth)}
                  </p>
                </div>
                <div className="rounded-full bg-emerald-100 px-4 py-2 text-sm font-semibold text-emerald-700 ring-1 ring-emerald-200">
                  {trendDelta === 0 ? "穩定" : formatPercent(trendDelta)}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-5">
                  <p className="text-sm text-slate-500">總資產</p>
                  <p className="mt-3 text-2xl font-semibold text-slate-950">
                    NT$ {formatCurrency(summary.totalAssets)}
                  </p>
                </div>
                <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-5">
                  <p className="text-sm text-slate-500">總負債</p>
                  <p className="mt-3 text-2xl font-semibold text-slate-950">
                    NT$ {formatCurrency(summary.totalLiabilities)}
                  </p>
                </div>
              </div>

              <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-5">
                <p className="text-sm font-medium text-slate-600">操作小提醒</p>
                <p className="mt-3 text-sm leading-6 text-slate-600">
                  使用頂部按鈕可立即拉取最新報價，並透過展開表單快速新增或調整帳戶資料。
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-[2rem] border border-slate-200/70 bg-white/90 p-6 shadow-[0_22px_50px_-24px_rgba(15,23,42,0.22)]">
            <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500">資產趨勢</p>
                <p className="text-xs text-slate-400">以台北時間 23:59 為計算截止</p>
              </div>
              <div className="flex flex-wrap rounded-full border border-slate-200 bg-white p-1">
                {(["day", "month", "quarter", "year"] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setTimeframe(item)}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition ${timeframe === item ? "bg-emerald-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}
                  >
                    {item === "day" ? "日" : item === "month" ? "月" : item === "quarter" ? "季" : "年"}
                  </button>
                ))}
              </div>
            </div>
            <div className="h-[360px] min-h-[18rem]">
              {mounted ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="netWorthGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#10b981" stopOpacity={0.32} />
                        <stop offset="100%" stopColor="#10b981" stopOpacity={0.06} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="label"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#64748b", fontSize: 12 }}
                      interval={0}
                    />
                    <YAxis
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#64748b", fontSize: 12 }}
                      width={55}
                    />
                    <Tooltip formatter={(value) => [`NT$ ${formatCurrency(Number(value ?? 0))}`, "淨資產"]} />
                    <Area type="monotone" dataKey="netWorth" stroke="#10b981" strokeWidth={3} fill="url(#netWorthGradient)" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[360px]" />
              )}
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.3fr_0.85fr]">
          <div className="space-y-6">
            {renderedAccountGroups.length === 0 ? (
              <div className="rounded-[1.5rem] border border-dashed border-slate-300 bg-white/70 p-6 text-sm text-slate-500 shadow-sm">
                目前還沒有任何資產，先新增第一筆就能開始看見你的財務視覺化。
              </div>
            ) : null}

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {renderedAccountGroups.map((group) => {
                if (!group) {
                  return null;
                }

                const isCollapsed = collapsedGroups[group.title] ?? (group.cards.length > 2 || ["【固定資產】", "【負債與應付款】"].includes(group.title));
                const groupTotal = group.cards.reduce((sum, card) => sum + Number(card.currentValue ?? 0), 0);

                return (
                  <Card key={group.title} className="border-slate-200/80 bg-white/80 shadow-sm">
                    <CardHeader className="flex items-start justify-between gap-4 pb-3">
                      <div className="min-w-0">
                        <div className={`h-1.5 w-16 rounded-full bg-gradient-to-r ${group.accent}`} />
                        <CardTitle className="mt-3 text-lg">{group.title}</CardTitle>
                        <CardDescription>
                          {group.cards.length} 項 · NT$ {formatCurrency(groupTotal)}
                        </CardDescription>
                      </div>
                      <button
                        type="button"
                        onClick={() => toggleGroup(group.title)}
                        className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 transition hover:bg-slate-50"
                        aria-label={isCollapsed ? "展開項目" : "收起項目"}
                      >
                        {isCollapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
                      </button>
                    </CardHeader>

                    {!isCollapsed ? (
                      <CardContent className="space-y-3">
                        {group.cards.map((card) => (
                          <div key={card.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0 flex-1">
                                <p className="text-sm font-semibold text-slate-900">{card.title}</p>
                                <p className="mt-1 text-xs text-slate-500">{card.subtitle}</p>
                                {card.accountCount > 1 ? (
                                  <p className="mt-1 text-[11px] text-slate-400">已合併 {card.accountCount} 筆相同標的與帳戶</p>
                                ) : null}
                                {symbolRequiredCategories.includes(card.category) ? (
                                  <p className="mt-1 text-[11px] text-slate-400">
                                    持有 {formatCurrency(card.quantity)} 股
                                  </p>
                                ) : (
                                  <p className="mt-1 text-[11px] text-slate-400">
                                    餘額 {formatCurrency(card.quantity)}
                                  </p>
                                )}
                              </div>
                              <div className="flex flex-col items-end gap-2">
                                <p className="text-sm font-semibold text-slate-900">
                                  NT$ {formatCurrency(Number(card.currentValue ?? 0))}
                                </p>
                                <div className="flex items-center gap-1">
                                  <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={() => startEdit(card.account)}>
                                    <Pencil className="mr-1 h-3.5 w-3.5" />
                                    編輯
                                  </Button>
                                  <Button variant="ghost" size="sm" className="h-8 px-2 text-xs text-rose-600" onClick={() => void handleDelete(card.account.id)}>
                                    <Trash2 className="mr-1 h-3.5 w-3.5" />
                                    刪除
                                  </Button>
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </CardContent>
                    ) : null}
                  </Card>
                );
              })}
            </div>
          </div>

          <div className="space-y-6">
            <Card className="border-slate-200/80 bg-white/80 shadow-sm">
              <CardHeader>
                <CardTitle>最近動態</CardTitle>
                <CardDescription>最近 20 筆交易與自動扣款紀錄。</CardDescription>
              </CardHeader>
              <CardContent>
                {transactions.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                    尚無交易紀錄，新增帳戶後即可開始累積活動流。
                  </div>
                ) : (
                  <div className="space-y-3">
                    {transactions.map((transaction) => (
                      <div key={transaction.id} className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3">
                        <div>
                          <p className="text-sm font-semibold text-slate-900">{transaction.account?.name || "未知帳戶"}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            {new Date(transaction.date).toLocaleString("zh-TW")}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-semibold text-slate-900">{transaction.type}</p>
                          <p className="mt-1 text-xs text-slate-500">NT$ {formatCurrency(transaction.amount)}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </section>
      </div>
    </main>

    {showForm ? (
      <div className="fixed inset-0 z-50 flex min-h-screen items-center justify-center bg-slate-900/40 backdrop-blur-sm px-4 py-6" onClick={() => setShowForm(false)}>
        <div className="relative w-full max-w-2xl overflow-hidden rounded-[2rem] border border-slate-200/80 bg-white/95 p-6 shadow-2xl shadow-slate-900/20" onClick={(event) => event.stopPropagation()}>
          <button
            type="button"
            onClick={() => {
              resetForm();
              setShowForm(false);
            }}
            className="absolute right-4 top-4 inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-slate-100 text-slate-700 transition hover:bg-slate-200"
            aria-label="關閉表單"
          >
            ✕
          </button>

          <div className="mb-6 space-y-2">
            <p className="text-sm font-medium uppercase tracking-[0.3em] text-emerald-600">新增項目</p>
            <h2 className="text-2xl font-semibold text-slate-950">{editingAccountId ? "編輯資產 / 負債" : "新增資產 / 負債"}</h2>
            <p className="text-sm text-slate-600">調整或新增帳戶資料，完成後表單將自動關閉。</p>
          </div>

          <Form onSubmit={handleSubmit} className="space-y-4">
            <FormItem>
              <FormLabel htmlFor="name">名稱</FormLabel>
              <FormControl>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(event) => setFormData({ ...formData, name: event.target.value })}
                  placeholder="例如：現金帳戶、台積電、BTC"
                />
              </FormControl>
            </FormItem>

            <div className="grid gap-4 lg:grid-cols-2">
              <FormItem>
                <FormLabel htmlFor="type">類型</FormLabel>
                <FormControl>
                  <select
                    id="type"
                    value={formData.type}
                    onChange={(event) => setFormData({ ...formData, type: event.target.value })}
                    className="flex h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition focus:border-slate-600 focus:ring-2 focus:ring-slate-200"
                  >
                    {typeOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </FormControl>
              </FormItem>

              <FormItem>
                <FormLabel htmlFor="category">類別</FormLabel>
                <FormControl>
                  <select
                    id="category"
                    value={formData.category}
                    onChange={(event) => {
                      const nextCategory = event.target.value;
                      const nextIsApiConnected = nextCategory === "CRYPTO" ? formData.isApiConnected : false;
                      setFormData({
                        ...formData,
                        category: nextCategory,
                        symbol: symbolRequiredCategories.includes(nextCategory) ? formData.symbol : "",
                        isApiConnected: nextIsApiConnected,
                        apiSource: nextCategory === "CRYPTO" ? formData.apiSource : "BITFINEX",
                        apiKey: nextCategory === "CRYPTO" ? formData.apiKey : "",
                        apiSecret: nextCategory === "CRYPTO" ? formData.apiSecret : "",
                      });
                    }}
                    className="flex h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition focus:border-slate-600 focus:ring-2 focus:ring-slate-200"
                  >
                    {categoryOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </FormControl>
              </FormItem>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <FormItem>
                <FormLabel htmlFor="currency">幣別</FormLabel>
                <FormControl>
                  <select
                    id="currency"
                    value={formData.currency}
                    onChange={(event) => setFormData({ ...formData, currency: event.target.value })}
                    className="flex h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition focus:border-slate-600 focus:ring-2 focus:ring-slate-200"
                  >
                    {currencyOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </FormControl>
              </FormItem>

              {!showApiFields ? (
                <FormItem>
                  <FormLabel htmlFor="quantity">
                    {usesAmountInput ? "總金額" : "持有股數"}
                  </FormLabel>
                  <FormControl>
                    <Input
                      id="quantity"
                      type="number"
                      step="any"
                      value={formData.quantity}
                      onChange={(event) => setFormData({ ...formData, quantity: event.target.value })}
                      placeholder={usesAmountInput ? "例如：10000、5000" : "例如：100、0.5"}
                    />
                  </FormControl>
                </FormItem>
              ) : null}
            </div>

            {formData.category === "CRYPTO" ? (
              <FormItem className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start gap-3">
                  <input
                    id="isApiConnected"
                    type="checkbox"
                    checked={formData.isApiConnected}
                    onChange={(event) => setFormData({ ...formData, isApiConnected: event.target.checked })}
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <div>
                    <FormLabel htmlFor="isApiConnected">🔌 串接交易所 API (自動同步餘額)</FormLabel>
                    <FormDescription>啟用後將由交易所 API 取得總資產估值，並自動更新台幣金額。</FormDescription>
                  </div>
                </div>
              </FormItem>
            ) : null}

            {showApiFields ? (
              <div className="grid gap-4 lg:grid-cols-2">
                <FormItem>
                  <FormLabel htmlFor="apiSource">交易所</FormLabel>
                  <FormControl>
                    <select
                      id="apiSource"
                      value={formData.apiSource}
                      onChange={(event) => setFormData({ ...formData, apiSource: event.target.value })}
                      className="flex h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition focus:border-slate-600 focus:ring-2 focus:ring-slate-200"
                    >
                      <option value="BITFINEX">BITFINEX</option>
                    </select>
                  </FormControl>
                </FormItem>

                <FormItem>
                  <FormLabel htmlFor="apiKey">API Key</FormLabel>
                  <FormControl>
                    <Input
                      id="apiKey"
                      value={formData.apiKey}
                      onChange={(event) => setFormData({ ...formData, apiKey: event.target.value })}
                      placeholder="請輸入 Bitfinex API Key"
                    />
                  </FormControl>
                </FormItem>

                <FormItem>
                  <FormLabel htmlFor="apiSecret">API Secret</FormLabel>
                  <FormControl>
                    <Input
                      id="apiSecret"
                      type="password"
                      value={formData.apiSecret}
                      onChange={(event) => setFormData({ ...formData, apiSecret: event.target.value })}
                      placeholder="請輸入 Bitfinex API Secret"
                    />
                  </FormControl>
                </FormItem>
              </div>
            ) : null}

            {requiresSymbol ? (
              <FormItem>
                <FormLabel htmlFor="symbol">代號 (Symbol)</FormLabel>
                <FormControl>
                  <Input
                    id="symbol"
                    value={formData.symbol}
                    onChange={(event) => setFormData({ ...formData, symbol: event.target.value })}
                    placeholder="例如：2330.TW、AAPL、BTC"
                  />
                </FormControl>
                <FormDescription>股票或虛擬貨幣類別需要填寫代號。</FormDescription>
              </FormItem>
            ) : null}

            {showDeductionFields ? (
              <div className="grid gap-4">
                <FormItem>
                  <FormLabel htmlFor="monthlyDeductionAmount">每月扣款金額</FormLabel>
                  <FormControl>
                    <Input
                      id="monthlyDeductionAmount"
                      type="number"
                      step="any"
                      value={formData.monthlyDeductionAmount}
                      onChange={(event) => setFormData({ ...formData, monthlyDeductionAmount: event.target.value })}
                      placeholder="例如：5000"
                    />
                  </FormControl>
                </FormItem>
                <FormItem>
                  <FormLabel htmlFor="deductionDate">每月扣款日 (1-31)</FormLabel>
                  <FormControl>
                    <Input
                      id="deductionDate"
                      type="number"
                      min="1"
                      max="31"
                      value={formData.deductionDate}
                      onChange={(event) => setFormData({ ...formData, deductionDate: event.target.value })}
                      placeholder="例如：15"
                    />
                  </FormControl>
                </FormItem>
              </div>
            ) : null}

            {error ? <FormMessage>{error}</FormMessage> : null}
            {message ? <p className="text-sm text-emerald-600">{message}</p> : null}

            <div className="flex flex-wrap justify-end gap-3 pt-4">
              <Button type="button" variant="outline" onClick={() => {
                resetForm();
                setShowForm(false);
              }}>
                取消
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? "儲存中..." : editingAccountId ? "儲存修改" : "新增帳戶"}
              </Button>
            </div>
          </Form>
        </div>
      </div>
    ) : null}
  </>
);
}
