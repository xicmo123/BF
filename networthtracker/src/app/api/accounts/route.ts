import { NextResponse } from "next/server"
import { PrismaClient } from "@prisma/client"

declare global {
  // eslint-disable-next-line no-var
  var prisma: PrismaClient | undefined
}

const prisma = globalThis.prisma || new PrismaClient()
if (process.env.NODE_ENV !== "production") globalThis.prisma = prisma

const categoriesRequiringSymbol = ["TAIWAN_STOCK", "US_STOCK", "CRYPTO"]

export async function GET() {
  const accounts = await prisma.account.findMany({
    orderBy: {
      createdAt: "desc",
    },
  })

  return NextResponse.json(accounts)
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => null)

  if (!body || typeof body !== "object") {
    return NextResponse.json({ message: "Invalid JSON payload." }, { status: 400 })
  }

  const { name, type, category, symbol, quantity, currency } = body as {
    name?: string
    type?: string
    category?: string
    symbol?: string
    quantity?: number | string
    currency?: string
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

  const account = await prisma.account.create({
    data: {
      name: name.trim(),
      type: type as any,
      category: category as any,
      symbol: trimmedSymbol || null,
      quantity: quantityValue,
      currency: currency as any,
    },
  })

  return NextResponse.json(account, { status: 201 })
}