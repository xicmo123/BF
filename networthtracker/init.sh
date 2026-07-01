#!/bin/bash

# NetWorthTracker Project Initialization Script
# This script sets up the project from scratch

set -e

echo "🚀 Initializing NetWorthTracker project..."

# Step 1: Install dependencies
echo "📦 Installing dependencies..."
npm install

# Step 2: Install additional dependencies
echo "📦 Installing additional dependencies..."
npm install prisma @prisma/client yahoo-finance2 node-cron date-fns recharts

# Step 3: Initialize shadcn/ui
echo "🎨 Initializing shadcn/ui..."
npx shadcn@latest init -y

# Step 4: Initialize Prisma
echo "🗄️  Initializing Prisma..."
npx prisma init --datasource-provider sqlite

# Step 5: Run Prisma migration
echo "🔄 Running Prisma migration..."
npx prisma migrate dev --name init

# Step 6: Generate Prisma Client
echo "⚙️  Generating Prisma Client..."
npx prisma generate

echo "✅ Project initialization complete!"
echo ""
echo "Next steps:"
echo "1. Review the Prisma schema in prisma/schema.prisma"
echo "2. Run 'npm run dev' to start the development server"
echo "3. Visit http://localhost:3000 to see the app"
