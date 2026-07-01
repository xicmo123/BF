import { NextResponse } from "next/server"
import yahooFinance from "yahoo-finance2"
import { PrismaClient } from "@prisma/client"

declare global {
  // eslint-disable-next-line no-var
  var prisma: PrismaClient | undefined
}

const prisma = globalThis.prisma || new PrismaClient()
if (process.env.NODE_ENV !== "production") globalThis.prisma = prisma

const categoriesRequiringSymbol = ["TAIWAN_STOCK", "US_STOCK", "CRYPTO"]
const fixedValueCategories = ["CASH", "BANK_ACCOUNT", "FIXED_ASSET", "RECEIVABLE", "PAYABLE", "MORTGAGE", "CAR_LOAN", "CREDIT_LOAN"]

async function fetchMarketPrice(category: string, symbol: string) {
  const yahoo = new yahooFinance()

  if (category === "CRYPTO") {
    const normalizedSymbol = symbol.toUpperCase()
    const cryptoResponse = await fetch(
      "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
    )

    if (!cryptoResponse.ok) {
      throw new Error(`CoinGecko API returned ${cryptoResponse.status}`)
    }

    const cryptoData = await cryptoResponse.json()
    const usdPrice =
      normalizedSymbol === "BTC" || normalizedSymbol === "BITCOIN"
        ? Number(cryptoData.bitcoin?.usd || 0)
        : normalizedSymbol === "ETH" || normalizedSymbol === "ETHEREUM"
          ? Number(cryptoData.ethereum?.usd || 0)
          : 0

    if (!usdPrice) {
      throw new Error(`Unsupported or missing crypto price for ${symbol}`)
    }

    const usdToTwdResult = await yahoo.quote("TWD=X")
    const usdToTwdRate = Number(usdToTwdResult.regularMarketPrice || 1)
    return usdPrice * usdToTwdRate
  }

  const quoteResult = await yahoo.quote(symbol)
  const marketPrice = Number(quoteResult.regularMarketPrice || 0)

  if (category === "US_STOCK") {
    const usdToTwdResult = await yahoo.quote("TWD=X")
    const usdToTwdRate = Number(usdToTwdResult.regularMarketPrice || 1)
    return marketPrice * usdToTwdRate
  }

  return marketPrice
}

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await request.json().catch(() => null)

  if (!body || typeof body !== "object") {
    return NextResponse.json({ message: "Invalid JSON payload." }, { status: 400 })
  }

  const { name, type, category, symbol, quantity, currency, monthlyDeductionAmount, deductionDate } = body as {
    name?: string
    type?: string
    category?: string
    symbol?: string
    quantity?: number | string
    currency?: string
    monthlyDeductionAmount?: number | string
    deductionDate?: number | string
    deductFromAccountId?: string | null
  }

  if (!name || !type || !category || !currency) {
    return NextResponse.json(
      { message: "Please provide name, type, category, and currency." },
      { status: 400 }
    )
  }

  const trimmedSymbol = typeof symbol === "string" ? symbol.trim() : ""
  if (categoriesRequiringSymbol.includes(category) && !trimmedSymbol) {
    return NextResponse.json(
      { message: "Stocks and crypto accounts require a symbol." },
      { status: 400 }
    )
  }

  const quantityValue =
    quantity === undefined || quantity === null || quantity === ""
      ? 0
      : Number(quantity)

  if (Number.isNaN(quantityValue)) {
    return NextResponse.json(
      { message: "Quantity must be a valid number." },
      { status: 400 }
    )
  }

  let deductionAmountValue: number | null = null
  let deductionDateValue: number | null = null

  if (type === "LIABILITY") {
    deductionAmountValue =
      monthlyDeductionAmount === undefined || monthlyDeductionAmount === null || monthlyDeductionAmount === ""
        ? null
        : Number(monthlyDeductionAmount)

    deductionDateValue =
      deductionDate === undefined || deductionDate === null || deductionDate === ""
        ? null
        : Number(deductionDate)

    if (deductionAmountValue !== null && Number.isNaN(deductionAmountValue)) {
      return NextResponse.json(
        { message: "Monthly deduction amount must be a valid number." },
        { status: 400 }
      )
    }

    if (deductionDateValue !== null && (!Number.isInteger(deductionDateValue) || deductionDateValue < 1 || deductionDateValue > 31)) {
      return NextResponse.json(
        { message: "Deduction date must be between 1 and 31." },
        { status: 400 }
      )
    }
  }

  const existingAccount = await prisma.account.findUnique({ where: { id } })
  if (!existingAccount) {
    return NextResponse.json({ message: "Account not found." }, { status: 404 })
  }

  let nextCurrentPrice = existingAccount.currentPrice ?? 0
  let nextCurrentValue = quantityValue

  if (categoriesRequiringSymbol.includes(category)) {
    try {
      const fetchedPrice = await fetchMarketPrice(category, trimmedSymbol)
      nextCurrentPrice = Number(fetchedPrice || 0)
      nextCurrentValue = quantityValue * nextCurrentPrice
    } catch (error) {
      console.error("Failed to refresh market price for updated account:", error)
      nextCurrentPrice = existingAccount.currentPrice ?? 0
      nextCurrentValue = quantityValue * (existingAccount.currentPrice ?? 0)
    }
  } else if (fixedValueCategories.includes(category)) {
    nextCurrentPrice = 1
    nextCurrentValue = quantityValue
  }

  const updatedAccount = await prisma.account.update({
    where: { id },
    data: {
      name: name.trim(),
      type: type as any,
      category: category as any,
      symbol: trimmedSymbol || null,
      quantity: quantityValue,
      currency: currency as any,
      currentPrice: nextCurrentPrice,
      currentValue: nextCurrentValue,
      monthlyDeductionAmount: deductionAmountValue,
      deductionDate: deductionDateValue,
    },
  })

  return NextResponse.json(updatedAccount, { status: 200 })
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params

  const existingAccount = await prisma.account.findUnique({ where: { id } })
  if (!existingAccount) {
    return NextResponse.json({ message: "Account not found." }, { status: 404 })
  }

  const updatedAccount = await prisma.account.update({
    where: { id },
    data: {
      isActive: false,
    },
  })

  return NextResponse.json(updatedAccount, { status: 200 })
}
