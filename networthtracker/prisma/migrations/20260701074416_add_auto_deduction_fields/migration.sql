-- AlterTable
ALTER TABLE "Account" ADD COLUMN "deductFromAccountId" TEXT;
ALTER TABLE "Account" ADD COLUMN "deductionDate" INTEGER;
ALTER TABLE "Account" ADD COLUMN "monthlyDeductionAmount" REAL;
