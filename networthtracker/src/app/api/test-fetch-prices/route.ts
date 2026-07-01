import { createHmac } from 'node:crypto';
import { NextResponse } from 'next/server';
import yahooFinance from 'yahoo-finance2';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

function normalizeCurrencyCode(value: string | null | undefined) {
  return String(value ?? '').toUpperCase();
}

function getNumericValue(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  return 0;
}

function buildBitfinexAuthHeaders(apiKey: string, apiSecret: string, requestPath: string) {
  const nonce = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  const requestBody = JSON.stringify({ request: requestPath, nonce });
  const signaturePayload = `${nonce}${requestPath}${requestBody}`;
  const signature = createHmac('sha384', apiSecret).update(signaturePayload).digest('hex');

  return {
    'Content-Type': 'application/json',
    'bfx-apikey': apiKey,
    'bfx-nonce': nonce,
    'bfx-signature': signature,
  };
}

async function fetchCryptoUsdPrices() {
  const response = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether,usd-coin&vs_currencies=usd');
  if (!response.ok) {
    throw new Error(`CoinGecko API returned ${response.status}`);
  }

  const data = await response.json() as Record<string, { usd?: number }>;
  return {
    BTC: Number(data.bitcoin?.usd || 0),
    ETH: Number(data.ethereum?.usd || 0),
    USDT: Number(data.tether?.usd || 1),
    USDC: Number(data['usd-coin']?.usd || 1),
  };
}

function parseBitfinexWallets(rawWallets: unknown) {
  if (!Array.isArray(rawWallets)) {
    return [] as Array<{ currency: string; balance: number }>;
  }

  return rawWallets
    .map((entry) => {
      if (Array.isArray(entry)) {
        const currency = normalizeCurrencyCode(entry[1] as string | undefined);
        const balance = getNumericValue(entry[2] ?? entry[3]);
        return currency && balance !== 0 ? { currency, balance } : null;
      }

      if (entry && typeof entry === 'object') {
        const maybe = entry as { currency?: string; curr?: string; balance?: unknown; amount?: unknown; available?: unknown };
        const currency = normalizeCurrencyCode(maybe.currency ?? maybe.curr);
        const balance = getNumericValue(maybe.balance ?? maybe.amount ?? maybe.available);
        return currency && balance !== 0 ? { currency, balance } : null;
      }

      return null;
    })
    .filter((entry): entry is { currency: string; balance: number } => Boolean(entry));
}

async function syncBitfinexAccount(account: { id: string; apiKey: string | null; apiSecret: string | null }, usdToTwdRate: number, cryptoPrices: Record<string, number>) {
  if (!account.apiKey || !account.apiSecret) {
    return null;
  }

  const headers = buildBitfinexAuthHeaders(account.apiKey, account.apiSecret, '/v2/auth/r/wallets');
  const response = await fetch('https://api.bitfinex.com/v2/auth/r/wallets', {
    method: 'POST',
    headers,
    body: JSON.stringify({ request: '/v2/auth/r/wallets' }),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`Bitfinex wallets API returned ${response.status}: ${text}`);
  }

  const wallets = await response.json();
  const parsedWallets = parseBitfinexWallets(wallets);

  let usdValue = 0;
  for (const wallet of parsedWallets) {
    const currency = normalizeCurrencyCode(wallet.currency);
    if (currency === 'USD') {
      usdValue += wallet.balance;
      continue;
    }

    if (currency === 'USDT' || currency === 'USDC') {
      usdValue += wallet.balance;
      continue;
    }

    if (currency === 'BTC' || currency === 'ETH') {
      const price = cryptoPrices[currency] || 0;
      usdValue += wallet.balance * price;
      continue;
    }
  }

  const twdValue = usdValue * Number(usdToTwdRate || 1);

  await prisma.account.update({
    where: { id: account.id },
    data: {
      currentPrice: twdValue,
      currentValue: twdValue,
    },
  });

  return {
    usdValue,
    twdValue,
    wallets: parsedWallets,
  };
}

export async function GET() {
  const results = {
    timestamp: new Date().toISOString(),
    taiwanStock: null as any,
    usStock: null as any,
    crypto: null as any,
    databaseUpdate: null as any,
    errors: [] as string[],
  };

  try {
    // 1. 測試台股：2330.TW (台積電)
    console.log('Fetching Taiwan Stock: 2330.TW');
    const yahoo = new yahooFinance();
    const taiwanStockResult = await yahoo.quote('2330.TW');
    results.taiwanStock = {
      symbol: taiwanStockResult.symbol,
      name: taiwanStockResult.longName,
      price: taiwanStockResult.regularMarketPrice,
      currency: taiwanStockResult.currency,
      marketCap: taiwanStockResult.marketCap,
    };
    console.log('Taiwan Stock fetched:', results.taiwanStock);
  } catch (error) {
    const errorMsg = `Taiwan Stock error: ${error instanceof Error ? error.message : String(error)}`;
    results.errors.push(errorMsg);
    console.error(errorMsg);
  }

  let usdToTwdRate = 1;

  try {
    // 2. 抓取 USD/TWD 匯率與美股：AAPL (蘋果)
    console.log('Fetching USD/TWD rate and US Stock: AAPL');
    const yahoo = new yahooFinance();
    const [usdToTwdResult, usStockResult] = await Promise.all([
      yahoo.quote('TWD=X'),
      yahoo.quote('AAPL'),
    ]);

    usdToTwdRate = Number(usdToTwdResult.regularMarketPrice || 1);

    results.usStock = {
      symbol: usStockResult.symbol,
      name: usStockResult.longName,
      price: usStockResult.regularMarketPrice,
      currency: usStockResult.currency,
      marketCap: usStockResult.marketCap,
      usdToTwdRate,
    };
    console.log('US Stock fetched:', results.usStock);
  } catch (error) {
    const errorMsg = `US Stock error: ${error instanceof Error ? error.message : String(error)}`;
    results.errors.push(errorMsg);
    console.error(errorMsg);
  }

  try {
    // 3. 測試虛擬貨幣：BTC 和 ETH (CoinGecko API)
    console.log('Fetching Crypto prices from CoinGecko');
    const cryptoResponse = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd'
    );

    if (!cryptoResponse.ok) {
      throw new Error(`CoinGecko API returned ${cryptoResponse.status}`);
    }

    const cryptoData = await cryptoResponse.json();
    results.crypto = {
      bitcoin: {
        symbol: 'BTC',
        price: cryptoData.bitcoin?.usd,
        currency: 'USD',
      },
      ethereum: {
        symbol: 'ETH',
        price: cryptoData.ethereum?.usd,
        currency: 'USD',
      },
    };
    console.log('Crypto prices fetched:', results.crypto);
  } catch (error) {
    const errorMsg = `Crypto error: ${error instanceof Error ? error.message : String(error)}`;
    results.errors.push(errorMsg);
    console.error(errorMsg);
  }

  try {
    console.log('Updating database with new prices...');

    const updates = [] as Array<{ symbol: string; updatedCount: number }>;
    const cryptoPrices = await fetchCryptoUsdPrices();

    // 更新台股價格
    if (results.taiwanStock?.price) {
      const accounts = await prisma.account.findMany({
        where: {
          symbol: '2330.TW',
          isActive: true,
        },
      });

      for (const account of accounts) {
        const currentValue = (account.quantity || 0) * results.taiwanStock.price;
        await prisma.account.update({
          where: { id: account.id },
          data: {
            currentPrice: results.taiwanStock.price,
            currentValue,
          },
        });
      }
      updates.push({ symbol: '2330.TW', updatedCount: accounts.length });
    }

    // 更新美股價格（換算為台幣）
    if (results.usStock?.price) {
      const accounts = await prisma.account.findMany({
        where: {
          symbol: 'AAPL',
          isActive: true,
        },
      });

      for (const account of accounts) {
        const currentPriceTwd = Number(results.usStock.price) * Number(usdToTwdRate || 1);
        const currentValue = (account.quantity || 0) * currentPriceTwd;
        await prisma.account.update({
          where: { id: account.id },
          data: {
            currentPrice: currentPriceTwd,
            currentValue,
          },
        });
      }
      updates.push({ symbol: 'AAPL', updatedCount: accounts.length });
    }

    // 更新 BTC 價格（換算為台幣）
    if (results.crypto?.bitcoin?.price) {
      const accounts = await prisma.account.findMany({
        where: {
          symbol: 'BTC',
          isActive: true,
        },
      });

      for (const account of accounts) {
        const currentPriceTwd = Number(results.crypto.bitcoin.price) * Number(usdToTwdRate || 1);
        const currentValue = (account.quantity || 0) * currentPriceTwd;
        await prisma.account.update({
          where: { id: account.id },
          data: {
            currentPrice: currentPriceTwd,
            currentValue,
          },
        });
      }
      updates.push({ symbol: 'BTC', updatedCount: accounts.length });
    }

    // 更新 ETH 價格（換算為台幣）
    if (results.crypto?.ethereum?.price) {
      const accounts = await prisma.account.findMany({
        where: {
          symbol: 'ETH',
          isActive: true,
        },
      });

      for (const account of accounts) {
        const currentPriceTwd = Number(results.crypto.ethereum.price) * Number(usdToTwdRate || 1);
        const currentValue = (account.quantity || 0) * currentPriceTwd;
        await prisma.account.update({
          where: { id: account.id },
          data: {
            currentPrice: currentPriceTwd,
            currentValue,
          },
        });
      }
      updates.push({ symbol: 'ETH', updatedCount: accounts.length });
    }

    const apiAccounts = await prisma.account.findMany({
      where: {
        isActive: true,
        isApiConnected: true,
        apiSource: 'BITFINEX',
        category: 'CRYPTO',
      },
    });

    for (const account of apiAccounts) {
      const synced = await syncBitfinexAccount(account, usdToTwdRate, cryptoPrices);
      if (synced) {
        updates.push({ symbol: `BITFINEX:${account.name}`, updatedCount: 1 });
      }
    }

    results.databaseUpdate = {
      message: 'Database update completed',
      updates,
    };
    console.log('Database update completed:', results.databaseUpdate);
  } catch (error) {
    const errorMsg = `Database update error: ${error instanceof Error ? error.message : String(error)}`;
    results.errors.push(errorMsg);
    console.error(errorMsg);
  }

  return NextResponse.json(results);
}
