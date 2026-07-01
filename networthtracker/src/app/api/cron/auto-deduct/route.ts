import { NextResponse } from "next/server";
import { PrismaClient } from "@prisma/client";

declare global {
  // eslint-disable-next-line no-var
  var prisma: PrismaClient | undefined;
}

const prisma = globalThis.prisma || new PrismaClient();
if (process.env.NODE_ENV !== "production") globalThis.prisma = prisma;

export async function GET() {
  const today = new Date();
  const deductionDay = today.getDate();

  try {
    const liabilities = await prisma.account.findMany({
      where: {
        type: "LIABILITY",
        isActive: true,
        deductionDate: deductionDay,
      },
    });

    if (liabilities.length === 0) {
      return NextResponse.json({
        message: "No liabilities due for automatic deduction today.",
        processedAccounts: [],
      });
    }

    const processedAccounts: Array<{ id: string; name: string }> = [];

    for (const liability of liabilities) {
      if (!liability.monthlyDeductionAmount || liability.monthlyDeductionAmount <= 0) {
        continue;
      }

      const deductionAmount = Number(liability.monthlyDeductionAmount);

      await prisma.$transaction(async (tx) => {
        if (liability.deductFromAccountId) {
          const sourceAccount = await tx.account.findUnique({
            where: { id: liability.deductFromAccountId },
          });

          if (sourceAccount) {
            await tx.account.update({
              where: { id: sourceAccount.id },
              data: {
                quantity: Number(sourceAccount.quantity ?? 0) - deductionAmount,
                currentValue: Number(sourceAccount.currentValue ?? 0) - deductionAmount,
              },
            });
          }
        }

        const updatedLiability = await tx.account.update({
          where: { id: liability.id },
          data: {
            quantity: Number(liability.quantity ?? 0) - deductionAmount,
            currentValue: Number(liability.currentValue ?? 0) - deductionAmount,
          },
        });

        await tx.transaction.create({
          data: {
            accountId: updatedLiability.id,
            type: "AUTO_DEDUCTION",
            amount: deductionAmount,
            description: `Automatic deduction for ${updatedLiability.name}`,
          },
        });
      });

      processedAccounts.push({ id: liability.id, name: liability.name });
    }

    return NextResponse.json({
      message: "Automatic deductions processed successfully.",
      processedAccounts,
    });
  } catch (error) {
    console.error("Auto deduction failed:", error);
    return NextResponse.json(
      { message: "Failed to process automatic deductions.", error: String(error) },
      { status: 500 }
    );
  }
}
