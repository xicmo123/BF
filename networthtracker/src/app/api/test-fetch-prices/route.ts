import { createHmac } from 'node:crypto';
import { NextResponse } from 'next/server';
import yahooFinance from 'yahoo-finance2';
import { PrismaClient } from '@prisma/client';

export const dynamic = 'force-dynamic';

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

function getYahooQuoteSymbol(category: string, symbol: string) {
  const normalizedSymbol = symbol.trim().toUpperCase();

  if (!normalizedSymbol) {
    return normalizedSymbol;
  }

  if (category === 'CRYPTO') {
    return normalizedSymbol.includes('-USD') ? normalizedSymbol : `${normalizedSymbol}-USD`;
  }

  return normalizedSymbol;
}

function buildBitfinexAuthHeaders(apiKey: string, apiSecret: string, requestPath: string, bodyObj: any = {}) {
  const nonce = (Date.now() * 1000).toString();
  const requestBody = JSON.stringify(bodyObj);
  const signaturePayload = `/api${requestPath}${nonce}${requestBody}`;
  const signature = createHmac('sha384', apiSecret).update(signaturePayload).digest('hex');

  return {
    'Content-Type': 'application/json',
    'bfx-nonce': nonce,
    'bfx-apikey': apiKey,
    'bfx-signature': signature,
  };
}

async function fetchCryptoUsdPrices() {
  const response = await fetch(
    'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether,usd-coin&vs_currencies=usd',
    { cache: 'no-store' }
  );

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

  const headers = buildBitfinexAuthHeaders(account.apiKey, account.apiSecret, '/v2/auth/r/wallets', {});
  const response = await fetch('https://api.bitfinex.com/v2/auth/r/wallets', {
    method: 'POST',
    headers,
    body: JSON.stringify({}),
    cache: 'no-store',
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
    manualUpdates: [] as Array<{ symbol: string; category: string; price: number; currentValue: number }> ,
    bitfinexUpdates: [] as Array<{ accountName: string; usdValue: number; twdValue: number }>,
    databaseUpdate: null as any,
    errors: [] as string[],
  };

  const yahoo = new yahooFinance();
  let usdToTwdRate = 1;

  try {
    const usdToTwdResult = await yahoo.quote('TWD=X');
    usdToTwdRate = Number(usdToTwdResult.regularMarketPrice || 1);
  } catch (error) {
    const errorMsg = `USD/TWD rate error: ${error instanceof Error ? error.message : String(error)}`;
    results.errors.push(errorMsg);
    console.error(errorMsg);
  }

  try {
    const manualAccounts = await prisma.account.findMany({
      where: {
        isActive: true,
        isApiConnected: false,
        category: {
          in: ['TAIWAN_STOCK', 'US_STOCK', 'CRYPTO'],
        },
      },
      orderBy: {
        createdAt: 'asc',
      },
    });

    for (const account of manualAccounts) {
      const symbol = account.symbol?.trim();
      if (!symbol) {
        continue;
      }

      try {
        const quoteSymbol = getYahooQuoteSymbol(account.category, symbol);
        const quoteResult = await yahoo.quote(quoteSymbol);
        const marketPrice = Number(quoteResult.regularMarketPrice || 0);

        if (!marketPrice) {
          continue;
        }

        const currentPrice = account.category === 'TAIWAN_STOCK' ? marketPrice : marketPrice * Number(usdToTwdRate || 1);
        const currentValue = (account.quantity || 0) * currentPrice;

        await prisma.account.update({
          where: { id: account.id },
          data: {
            currentPrice,
            currentValue,
          },
        });

        results.manualUpdates.push({
          symbol: quoteSymbol,
          category: account.category,
          price: currentPrice,
          currentValue,
        });
      } catch (error) {
        const errorMsg = `Quote error for ${account.symbol}: ${error instanceof Error ? error.message : String(error)}`;
        results.errors.push(errorMsg);
        console.error(errorMsg);
      }
    }
  } catch (error) {
    const errorMsg = `Manual account update error: ${error instanceof Error ? error.message : String(error)}`;
    results.errors.push(errorMsg);
    console.error(errorMsg);
  }

  try {
    const cryptoPrices = await fetchCryptoUsdPrices();
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
        results.bitfinexUpdates.push({
          accountName: account.name,
          usdValue: synced.usdValue,
          twdValue: synced.twdValue,
        });
      }
    }
  } catch (error) {
    const errorMsg = `Bitfinex sync error: ${error instanceof Error ? error.message : String(error)}`;
    results.errors.push(errorMsg);
    console.error(errorMsg);
  }

  results.databaseUpdate = {
    message: 'Database update completed',
    manualUpdates: results.manualUpdates.length,
    bitfinexUpdates: results.bitfinexUpdates.length,
  };

  return NextResponse.json(results);
}
