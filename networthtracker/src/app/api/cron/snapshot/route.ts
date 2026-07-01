import { NextResponse } from "next/server";
import { PrismaClient } from "@prisma/client";

declare global {
  // eslint-disable-next-line no-var
  var prisma: PrismaClient | undefined;
}

const prisma = globalThis.prisma || new PrismaClient();
if (process.env.NODE_ENV !== "production") globalThis.prisma = prisma;

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const shouldPersist = searchParams.get("write") !== "false";

  try {
    const accounts = await prisma.account.findMany({
      where: {
        isActive: true,
      },
    });

    const totalAssets = accounts
      .filter((account) => account.type === "ASSET")
      .reduce((sum, account) => sum + Number(account.currentValue ?? 0), 0);

    const totalLiabilities = accounts
      .filter((account) => account.type === "LIABILITY")
      .reduce((sum, account) => sum + Number(account.currentValue ?? 0), 0);

    const netWorth = totalAssets - totalLiabilities;

    const breakdown = JSON.stringify(
      accounts.map((account) => ({
        id: account.id,
        name: account.name,
        type: account.type,
        category: account.category,
        currentValue: account.currentValue,
      }))
    );

    const snapshotDate = new Date();
    snapshotDate.setHours(0, 0, 0, 0);

    const snapshot = {
      date: snapshotDate.toISOString(),
      totalAssets,
      totalLiabilities,
      netWorth,
      breakdown,
    };

    if (shouldPersist) {
      await prisma.assetHistory.upsert({
        where: { date: snapshotDate },
        update: {
          totalAssets,
          totalLiabilities,
          netWorth,
          breakdown,
        },
        create: {
          date: snapshotDate,
          totalAssets,
          totalLiabilities,
          netWorth,
          breakdown,
        },
      });
    }

    return NextResponse.json({
      message: shouldPersist ? "Snapshot recorded successfully." : "Snapshot preview generated.",
      snapshot,
    });
  } catch (error) {
    console.error("Snapshot creation failed:", error);
    return NextResponse.json(
      { message: "Failed to create snapshot.", error: String(error) },
      { status: 500 }
    );
  }
}
