import { NextResponse } from "next/server";
import { PrismaClient } from "@prisma/client";

declare global {
  // eslint-disable-next-line no-var
  var prisma: PrismaClient | undefined;
}

const prisma = globalThis.prisma || new PrismaClient();
if (process.env.NODE_ENV !== "production") globalThis.prisma = prisma;

export async function GET() {
  try {
    const transactions = await prisma.transaction.findMany({
      take: 20,
      orderBy: {
        date: "desc",
      },
      include: {
        account: true,
      },
    });

    return NextResponse.json(transactions);
  } catch (error) {
    console.error("Transactions lookup failed:", error);
    return NextResponse.json(
      { message: "Failed to fetch transactions.", error: String(error) },
      { status: 500 }
    );
  }
}
