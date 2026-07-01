import { NextResponse } from 'next/server';
import yahooFinance from 'yahoo-finance2';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

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
    // 4. 模擬更新資料庫中的 currentPrice
    console.log('Updating database with new prices...');
    
    const updates = [];
    
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
