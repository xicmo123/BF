"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Pencil, RefreshCw, Trash2 } from "lucide-react";
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
  currentPrice: number | null;
  currentValue: number;
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
  monthlyDeductionAmount: "",
  deductionDate: "",
  deductFromAccountId: "",
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
  const [showForm, setShowForm] = useState(true);
  const [editingAccountId, setEditingAccountId] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<"day" | "month" | "quarter" | "year">("day");
  const formSectionRef = useRef<HTMLDivElement | null>(null);

  const requiresSymbol = symbolRequiredCategories.includes(formData.category);
  const usesAmountInput = amountInputCategories.includes(formData.category);
  const showDeductionFields = formData.type === "LIABILITY";
  const sourceAccounts = accounts.filter(
    (account) => account.category === "CASH" || account.category === "BANK_ACCOUNT"
  );

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
    setShowForm(true);
  }

  function startEdit(account: Account) {
    setFormData({
      name: account.name,
      type: account.type,
      category: account.category,
      symbol: account.symbol ?? "",
      quantity: String(account.quantity ?? account.currentValue ?? 0),
      currency: account.currency,
      monthlyDeductionAmount: "",
      deductionDate: "",
      deductFromAccountId: "",
    });
    setEditingAccountId(account.id);
    setShowForm(true);
    setError(null);
    setMessage(null);
    setSyncMessage(null);
    requestAnimationFrame(() => {
      formSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
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

    const parsedQuantity = Number(formData.quantity ?? 0);
    if (Number.isNaN(parsedQuantity)) {
      setError("數量/餘額必須是有效數字。");
      return;
    }

    const payload = {
      name: formData.name.trim(),
      type: formData.type,
      category: formData.category,
      symbol: formData.symbol.trim() || null,
      quantity: parsedQuantity,
      currency: formData.currency,
      monthlyDeductionAmount: showDeductionFields ? Number(formData.monthlyDeductionAmount || 0) : null,
      deductionDate: showDeductionFields ? Number(formData.deductionDate || 0) : null,
      deductFromAccountId: showDeductionFields ? formData.deductFromAccountId || null : null,
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

  function buildFallbackHistory(currentNetWorth: number) {
    const base = Math.max(1000, Number(currentNetWorth || 10000));
    return Array.from({ length: 7 }, (_, index) => {
      const ratio = 1 - index * 0.035;
      const value = Math.max(1000, base * ratio);
      return {
        id: `fallback-${index}`,
        date: new Date(Date.now() - (6 - index) * 24 * 60 * 60 * 1000).toISOString(),
        totalAssets: value,
        totalLiabilities: Math.max(0, value * 0.08),
        netWorth: value,
      } as HistoryPoint;
    });
  }

  function buildChartSeries(historyPoints: HistoryPoint[], selectedTimeframe: typeof timeframe) {
    const sorted = [...historyPoints].sort(
      (left, right) => new Date(left.date).getTime() - new Date(right.date).getTime()
    );

    if (sorted.length === 0) {
      return buildFallbackHistory(summary.netWorth).map((point) => ({
        ...point,
        label: new Date(point.date).toLocaleDateString("zh-TW", { month: "numeric", day: "numeric" }),
      }));
    }

    if (selectedTimeframe === "day") {
      const source = sorted.slice(-7);
      return source.map((point) => ({
        ...point,
        label: new Date(point.date).toLocaleDateString("zh-TW", { month: "numeric", day: "numeric" }),
      }));
    }

    const grouped = new Map<string, HistoryPoint>();

    for (const point of sorted) {
      const date = new Date(point.date);
      let key = "";

      if (selectedTimeframe === "month") {
        key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
      } else if (selectedTimeframe === "quarter") {
        const quarter = Math.floor(date.getMonth() / 3) + 1;
        key = `${date.getFullYear()}-Q${quarter}`;
      } else {
        key = `${date.getFullYear()}`;
      }

      grouped.set(key, point);
    }

    return Array.from(grouped.entries())
      .slice(-12)
      .map(([key, point]) => ({
        ...point,
        label:
          selectedTimeframe === "month"
            ? key.replace("-", " / ")
            : selectedTimeframe === "quarter"
              ? key
              : key,
      }));
  }

  const accountGroups = [
    { title: "【流動資金】", categories: ["BANK_ACCOUNT", "CASH"], accent: "from-emerald-500 to-teal-500" },
    { title: "【投資組合】", categories: ["TAIWAN_STOCK", "US_STOCK", "CRYPTO"], accent: "from-sky-500 to-blue-500" },
    { title: "【固定資產】", categories: ["FIXED_ASSET"], accent: "from-amber-500 to-orange-500" },
    { title: "【應收款項】", categories: ["RECEIVABLE"], accent: "from-violet-500 to-fuchsia-500" },
    { title: "【負債與應付款】", categories: ["PAYABLE", "MORTGAGE", "CAR_LOAN", "CREDIT_LOAN"], accent: "from-rose-500 to-pink-500" },
  ];

  const chartData = useMemo(() => buildChartSeries(history, timeframe), [history, timeframe, summary.netWorth]);

  const trendDelta = useMemo(() => {
    if (chartData.length < 2) {
      return 0;
    }

    const firstValue = Number(chartData[0]?.netWorth ?? 0);
    const lastValue = Number(chartData[chartData.length - 1]?.netWorth ?? 0);

    if (!firstValue) {
      return 0;
    }

    return ((lastValue - firstValue) / firstValue) * 100;
  }, [chartData]);

  const renderedAccountGroups = useMemo(() => {
    return accountGroups
      .map((group) => {
        const relevantAccounts = accounts.filter((account) => group.categories.includes(account.category));
        if (relevantAccounts.length === 0) {
          return null;
        }

        const isInvestmentGroup = group.categories.some((category) => symbolRequiredCategories.includes(category));

        if (isInvestmentGroup) {
          return {
            ...group,
            cards: relevantAccounts.map((account) => ({
              id: account.id,
              name: account.name,
              category: account.category,
              account,
              label: `${categoryLabelMap[account.category] ?? account.category}${account.symbol ? ` · ${account.symbol}` : ""}`,
              quantity: Number(account.quantity ?? 0),
              currentValue: Number(account.currentValue ?? 0),
              accountCount: 1,
            })),
          };
        }

        const groupedCards = Object.values(
          relevantAccounts.reduce<Record<string, { id: string; name: string; category: string; label: string; quantity: number; currentValue: number; accountCount: number; account: Account }>>(
            (result, account) => {
              const key = account.name.trim().toLowerCase();
              if (!result[key]) {
                result[key] = {
                  id: `group-${key}`,
                  name: account.name,
                  category: account.category,
                  label: categoryLabelMap[account.category] ?? account.category,
                  quantity: 0,
                  currentValue: 0,
                  accountCount: 0,
                  account,
                };
              }

              result[key].quantity += Number(account.quantity ?? 0);
              result[key].currentValue += Number(account.currentValue ?? 0);
              result[key].accountCount += 1;
              result[key].label = result[key].accountCount > 1 ? `${result[key].label} · 多筆同名帳戶` : result[key].label;
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

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.12),_transparent_35%),linear-gradient(135deg,_#f8fafc_0%,_#f1f5f9_100%)] px-4 py-8 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <section className="rounded-[2rem] border border-slate-200/70 bg-white/80 p-6 shadow-[0_24px_80px_-32px_rgba(15,23,42,0.35)] backdrop-blur xl:p-8">
          <div className="flex flex-col gap-8 xl:flex-row xl:items-center xl:justify-between">
            <div className="max-w-2xl">
              <p className="text-sm font-medium uppercase tracking-[0.3em] text-emerald-600">
                NetWorthTracker
              </p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">
                淨資產一眼看懂，財務心智清爽。
              </h1>
              <p className="mt-4 max-w-xl text-base leading-7 text-slate-600">
                追蹤帳戶、匯率與自動扣款，讓現金流、投資組合與負債狀態變得清楚而可掌控。
              </p>
              <div className="mt-6 flex flex-wrap items-center gap-3">
                <Button onClick={handleSyncPrices} disabled={syncing} className="rounded-full">
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
                </Button>
                <Button variant="outline" className="rounded-full" onClick={() => setShowForm((value) => !value)}>
                  {showForm ? "收合新增表單" : "展開新增表單"}
                </Button>
              </div>
            </div>

            <div className="w-full max-w-xl rounded-[1.5rem] border border-slate-200 bg-slate-50/80 p-5 shadow-inner">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">目前淨資產</p>
                  <p className="mt-2 text-4xl font-semibold tracking-tight text-slate-950">
                    NT$ {formatCurrency(summary.netWorth)}
                  </p>
                </div>
                <div className="rounded-full bg-emerald-100 px-3 py-1 text-sm font-medium text-emerald-700">
                  {trendDelta === 0 ? "穩定" : formatPercent(trendDelta)}
                </div>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-sm text-slate-500">總資產</p>
                  <p className="mt-2 text-xl font-semibold text-slate-900">
                    NT$ {formatCurrency(summary.totalAssets)}
                  </p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-sm text-slate-500">總負債</p>
                  <p className="mt-2 text-xl font-semibold text-slate-900">
                    NT$ {formatCurrency(summary.totalLiabilities)}
                  </p>
                </div>
              </div>

              <div className="mt-5">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-slate-500">資產趨勢</p>
                  <div className="flex rounded-full border border-slate-200 bg-white p-1">
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
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="netWorthGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#10b981" stopOpacity={0.28} />
                          <stop offset="100%" stopColor="#10b981" stopOpacity={0.04} />
                        </linearGradient>
                      </defs>
                      <XAxis
                        dataKey="label"
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: "#64748b", fontSize: 12 }}
                      />
                      <YAxis
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: "#64748b", fontSize: 12 }}
                        width={50}
                      />
                      <Tooltip formatter={(value) => [`NT$ ${formatCurrency(Number(value ?? 0))}`, "淨資產"]} />
                      <Area type="monotone" dataKey="netWorth" stroke="#10b981" strokeWidth={2.5} fill="url(#netWorthGradient)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
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

                return (
                  <Card key={group.title} className="border-slate-200/80 bg-white/80 shadow-sm">
                    <CardHeader className="pb-3">
                      <div className={`h-1.5 w-16 rounded-full bg-gradient-to-r ${group.accent}`} />
                      <CardTitle className="mt-3 text-lg">{group.title}</CardTitle>
                      <CardDescription>{group.cards.length} 個卡片</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {group.cards.map((card) => (
                        <div key={card.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-semibold text-slate-900">{card.name}</p>
                              <p className="mt-1 text-xs text-slate-500">{card.label}</p>
                              {card.accountCount > 1 ? (
                                <p className="mt-1 text-[11px] text-slate-400">已合併 {card.accountCount} 個相同名稱帳戶</p>
                              ) : null}
                              {symbolRequiredCategories.includes(card.category) ? (
                                <p className="mt-1 text-[11px] text-slate-400">
                                  持有 {formatCurrency(card.quantity)} 單位 · 現價 NT$ {formatCurrency(Number(card.account.currentPrice ?? 0))}
                                </p>
                              ) : (
                                <p className="mt-1 text-[11px] text-slate-400">
                                  餘額 NT$ {formatCurrency(Number(card.currentValue ?? 0))}
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
                  </Card>
                );
              })}
            </div>
          </div>

          <div className="space-y-6">
            <Card className="border-slate-200/80 bg-white/80 shadow-sm">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>{editingAccountId ? "編輯資產 / 負債" : "新增資產 / 負債"}</CardTitle>
                  <CardDescription>{editingAccountId ? "調整名稱、金額或股數後儲存修改。" : "建立帳戶、設定扣款與來源帳戶。"}</CardDescription>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setShowForm((value) => !value)}>
                  {showForm ? "收合" : "展開"}
                </Button>
              </CardHeader>
              {showForm ? (
                <div ref={formSectionRef}>
                  <CardContent>
                    <Form onSubmit={handleSubmit}>
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

                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
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
                              setFormData({
                                ...formData,
                                category: nextCategory,
                                symbol: symbolRequiredCategories.includes(nextCategory) ? formData.symbol : "",
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

                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
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

                      <FormItem>
                        <FormLabel htmlFor="quantity">
                          {usesAmountInput ? "總金額 / 餘額" : "持有股數 / 數量"}
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
                    </div>

                    {requiresSymbol ? (
                      <FormItem className="mt-4">
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
                      <div className="mt-4 grid gap-4">
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
                        <FormItem>
                          <FormLabel htmlFor="deductFromAccountId">扣款來源帳戶</FormLabel>
                          <FormControl>
                            <select
                              id="deductFromAccountId"
                              value={formData.deductFromAccountId}
                              onChange={(event) => setFormData({ ...formData, deductFromAccountId: event.target.value })}
                              className="flex h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition focus:border-slate-600 focus:ring-2 focus:ring-slate-200"
                            >
                              <option value="">請選擇來源帳戶</option>
                              {sourceAccounts.map((account) => (
                                <option key={account.id} value={account.id}>
                                  {account.name}
                                </option>
                              ))}
                            </select>
                          </FormControl>
                        </FormItem>
                      </div>
                    ) : null}

                    {error ? <FormMessage className="mt-4">{error}</FormMessage> : null}
                    {message ? <p className="mt-4 text-sm text-emerald-600">{message}</p> : null}

                      <CardFooter className="mt-4 flex justify-end gap-2 border-t border-slate-200 px-0 pt-4">
                        {editingAccountId ? (
                          <Button type="button" variant="outline" onClick={resetForm}>
                            取消編輯
                          </Button>
                        ) : null}
                        <Button type="submit" disabled={loading}>
                          {loading ? "儲存中..." : editingAccountId ? "儲存修改" : "新增帳戶"}
                        </Button>
                      </CardFooter>
                    </Form>
                  </CardContent>
                </div>
              ) : null}
            </Card>

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
  );
}
