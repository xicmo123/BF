"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
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
  { value: "TAIWAN_STOCK", label: "台股" },
  { value: "US_STOCK", label: "美股" },
  { value: "CRYPTO", label: "虛擬貨幣" },
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
  TAIWAN_STOCK: "台股",
  US_STOCK: "美股",
  CRYPTO: "虛擬貨幣",
  MORTGAGE: "房貸",
  CAR_LOAN: "車貸",
  CREDIT_LOAN: "信用貸款",
};

const symbolRequiredCategories = ["TAIWAN_STOCK", "US_STOCK", "CRYPTO"];

const assetAllocationCategories = [
  { key: "CASH", label: "現金", color: "#10b981" },
  { key: "TAIWAN_STOCK", label: "台股", color: "#3b82f6" },
  { key: "US_STOCK", label: "美股", color: "#f59e0b" },
  { key: "CRYPTO", label: "虛擬貨幣", color: "#8b5cf6" },
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

const defaultForm = {
  name: "",
  type: "ASSET",
  category: "CASH",
  symbol: "",
  quantity: "0",
  currency: "TWD",
};

export default function HomePage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [formData, setFormData] = useState(defaultForm);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const requiresSymbol = symbolRequiredCategories.includes(formData.category);

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

  const allocationData = useMemo(() => {
    const totals = assetAllocationCategories.reduce(
      (acc, category) => {
        acc[category.key] = 0;
        return acc;
      },
      {} as Record<string, number>
    );

    accounts
      .filter((account) => account.type === "ASSET")
      .forEach((account) => {
        if (totals[account.category] !== undefined) {
          totals[account.category] += Number(account.currentValue ?? 0);
        }
      });

    return assetAllocationCategories
      .map((category) => ({
        category: category.key,
        name: category.label,
        value: totals[category.key],
        color: category.color,
      }))
      .filter((item) => item.value > 0);
  }, [accounts]);

  useEffect(() => {
    fetchAccounts();
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
        fetchError instanceof Error
          ? fetchError.message
          : "載入帳戶資料時發生錯誤。"
      );
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
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

    const payload = {
      name: formData.name.trim(),
      type: formData.type,
      category: formData.category,
      symbol: formData.symbol.trim() || null,
      quantity: Number(formData.quantity ?? 0),
      currency: formData.currency,
    };

    if (Number.isNaN(payload.quantity)) {
      setError("數量/餘額必須是有效數字。");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch("/api/accounts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.message || "儲存失敗。");
      }

      setMessage("已成功新增資產/負債。");
      setFormData(defaultForm);
      await fetchAccounts();
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "新增帳戶時發生錯誤。"
      );
    } finally {
      setLoading(false);
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
        throw new Error(result?.message || "同步最新報價失敗。")
      }

      await fetchAccounts();
      const updatedCount = result?.databaseUpdate?.updates?.length ?? 0;
      setSyncMessage(
        `已同步最新報價，成功更新 ${updatedCount} 類型的帳戶價格。`
      );
    } catch (syncError) {
      setError(
        syncError instanceof Error
          ? syncError.message
          : "同步最新報價時發生錯誤。"
      );
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

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 sm:px-6 lg:px-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <div>
          <h1 className="text-3xl font-semibold text-slate-950 dark:text-slate-50">
            NetWorthTracker
          </h1>
          <p className="mt-2 text-slate-600 dark:text-slate-400">
            新增資產 / 負債，並在下方查看目前帳戶清單。
          </p>
        </div>

        <Card className="border-slate-200 bg-white/80 shadow-sm">
          <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <CardTitle>總覽儀表板</CardTitle>
              <CardDescription>
                查看淨資產、負債與資產分布，並同步最新報價。
              </CardDescription>
            </div>
            <Button onClick={handleSyncPrices} disabled={syncing}>
              {syncing ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  同步中...
                </>
              ) : (
                <>
                  <RefreshCw className="mr-2 h-4 w-4" />
                  🔄 同步最新報價
                </>
              )}
            </Button>
          </CardHeader>
          <CardContent className="space-y-6">
            {syncMessage ? (
              <p className="text-sm text-emerald-600 dark:text-emerald-400">
                {syncMessage}
              </p>
            ) : null}

            <div className="grid gap-4 md:grid-cols-3">
              <Card className="border-slate-200 bg-slate-50 shadow-sm">
                <CardContent className="pt-6">
                  <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
                    總資產
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                    NT$ {formatCurrency(summary.totalAssets)}
                  </p>
                </CardContent>
              </Card>
              <Card className="border-slate-200 bg-slate-50 shadow-sm">
                <CardContent className="pt-6">
                  <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
                    總負債
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                    NT$ {formatCurrency(summary.totalLiabilities)}
                  </p>
                </CardContent>
              </Card>
              <Card className="border-slate-200 bg-slate-50 shadow-sm">
                <CardContent className="pt-6">
                  <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
                    淨資產
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-emerald-600 dark:text-emerald-400">
                    NT$ {formatCurrency(summary.netWorth)}
                  </p>
                </CardContent>
              </Card>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="mb-4 text-sm font-medium text-slate-700 dark:text-slate-300">
                資產分布
              </p>
              {allocationData.length === 0 ? (
                <div className="flex h-72 items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                  尚無足夠數據繪製圖表
                </div>
              ) : (
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={allocationData}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={70}
                        outerRadius={110}
                        paddingAngle={2}
                      >
                        {allocationData.map((item) => (
                          <Cell key={item.category} fill={item.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        formatter={(value) => [
                          `NT$ ${formatCurrency(Number(value ?? 0))}`,
                          "金額",
                        ]}
                      />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>新增資產 / 負債</CardTitle>
            <CardDescription>
              請填寫帳戶名稱與基本屬性，必要時提供股票或加密貨幣代號。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Form onSubmit={handleSubmit}>
              <FormItem>
                <FormLabel htmlFor="name">名稱</FormLabel>
                <FormControl>
                  <Input
                    id="name"
                    value={formData.name}
                    onChange={(event) =>
                      setFormData({ ...formData, name: event.target.value })
                    }
                    placeholder="例如：現金帳戶、台積電、BTC"
                  />
                </FormControl>
              </FormItem>

              <div className="grid gap-4 lg:grid-cols-3">
                <FormItem>
                  <FormLabel htmlFor="type">類型</FormLabel>
                  <FormControl>
                    <select
                      id="type"
                      value={formData.type}
                      onChange={(event) =>
                        setFormData({ ...formData, type: event.target.value })
                      }
                      className="flex h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition focus:border-slate-600 focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50 dark:focus:border-slate-400 dark:focus:ring-slate-700"
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
                          symbol: symbolRequiredCategories.includes(nextCategory)
                            ? formData.symbol
                            : "",
                        });
                      }}
                      className="flex h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition focus:border-slate-600 focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50 dark:focus:border-slate-400 dark:focus:ring-slate-700"
                    >
                      {categoryOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </FormControl>
                </FormItem>

                <FormItem>
                  <FormLabel htmlFor="currency">幣別</FormLabel>
                  <FormControl>
                    <select
                      id="currency"
                      value={formData.currency}
                      onChange={(event) =>
                        setFormData({ ...formData, currency: event.target.value })
                      }
                      className="flex h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition focus:border-slate-600 focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50 dark:focus:border-slate-400 dark:focus:ring-slate-700"
                    >
                      {currencyOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </FormControl>
                </FormItem>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                {requiresSymbol ? (
                  <FormItem>
                    <FormLabel htmlFor="symbol">代號</FormLabel>
                    <FormControl>
                      <Input
                        id="symbol"
                        value={formData.symbol}
                        onChange={(event) =>
                          setFormData({ ...formData, symbol: event.target.value })
                        }
                        placeholder="例如：2330.TW、AAPL、BTC"
                      />
                    </FormControl>
                    <FormDescription>
                      股票或虛擬貨幣類別需要填寫代號。
                    </FormDescription>
                  </FormItem>
                ) : null}

                <FormItem>
                  <FormLabel htmlFor="quantity">數量 / 餘額</FormLabel>
                  <FormControl>
                    <Input
                      id="quantity"
                      type="number"
                      step="any"
                      value={formData.quantity}
                      onChange={(event) =>
                        setFormData({ ...formData, quantity: event.target.value })
                      }
                      placeholder="例如：1000、1.5"
                    />
                  </FormControl>
                </FormItem>
              </div>

              {error ? <FormMessage>{error}</FormMessage> : null}
              {message ? (
                <p className="text-sm text-emerald-600 dark:text-emerald-400">
                  {message}
                </p>
              ) : null}

              <CardFooter className="flex justify-end border-t border-slate-200 pt-4 dark:border-slate-700">
                <Button type="submit" disabled={loading}>
                  {loading ? "儲存中..." : "新增資產 / 負債"}
                </Button>
              </CardFooter>
            </Form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>帳戶清單</CardTitle>
            <CardDescription>
              目前已建立的資產與負債帳戶將顯示於此。
            </CardDescription>
          </CardHeader>
          <CardContent>
            {accounts.length === 0 ? (
              <p className="text-sm text-slate-600 dark:text-slate-400">
                尚未建立任何帳戶。
              </p>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {accounts.map((account) => {
                  const typeLabel =
                    typeOptions.find((option) => option.value === account.type)
                      ?.label ?? account.type;
                  const statusClasses =
                    account.type === "ASSET"
                      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
                      : "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200";

                  return (
                    <Card
                      key={account.id}
                      className="border-slate-200 bg-slate-50 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="text-base font-semibold text-slate-950 dark:text-slate-50">
                            {account.name}
                          </p>
                          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                            {categoryLabelMap[account.category] ?? account.category}
                          </p>
                        </div>
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${statusClasses}`}
                        >
                          {typeLabel}
                        </span>
                      </div>
                      <div className="mt-4 space-y-3 text-sm text-slate-700 dark:text-slate-300">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">代號</span>
                          <span>{account.symbol || "-"}</span>
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">數量 / 餘額</span>
                          <span>{account.quantity ?? "-"}</span>
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">幣別</span>
                          <span>{account.currency}</span>
                        </div>
                        <div className="flex items-center justify-between gap-2 border-t border-slate-200 pt-3 text-sm font-semibold text-slate-950 dark:border-slate-700 dark:text-slate-50">
                          <span>目前價值</span>
                          <span>
                            {account.currentValue.toLocaleString(undefined, {
                              minimumFractionDigits: 0,
                              maximumFractionDigits: 2,
                            })}
                          </span>
                        </div>
                      </div>
                    </Card>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
