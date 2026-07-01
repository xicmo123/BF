#!/bin/bash

# Bitfinex Lending Bot - Server Setup Script
# This script automates the deployment of Dashboard systemd service and Bot cron job

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Get current user and project directory
ACTUAL_USER=${SUDO_USER:-$(whoami)}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

print_info "Starting server setup..."
print_info "User: $ACTUAL_USER"
print_info "Project Directory: $PROJECT_DIR"

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    print_error "Project directory does not exist: $PROJECT_DIR"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    print_error "Virtual environment not found at $PROJECT_DIR/.venv"
    print_error "Please create the virtual environment first"
    exit 1
fi

# ============================================================================
# 1. Dashboard Systemd Service Setup
# ============================================================================
print_info "Setting up Dashboard systemd service..."

SERVICE_FILE="/etc/systemd/system/bfx-dashboard.service"

# Create systemd service file
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Bitfinex Lending Bot Dashboard
After=network.target

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR
Environment="PYTHONPATH=src"
ExecStart=$PROJECT_DIR/.venv/bin/uvicorn bitfinex_lending_bot.dashboard_api:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

print_success "Service file created at $SERVICE_FILE"

# Reload systemd daemon
print_info "Reloading systemd daemon..."
systemctl daemon-reload

# Enable and start the service
print_info "Enabling bfx-dashboard service..."
systemctl enable bfx-dashboard.service

print_info "Starting bfx-dashboard service..."
systemctl start bfx-dashboard.service

print_success "Dashboard service is now running"

# ============================================================================
# 2. Bot Crontab Setup (with Idempotency Check)
# ============================================================================
print_info "Setting up Bot cron job..."

# Define the cron job
CRON_JOB="*/5 * * * * cd $PROJECT_DIR && PYTHONPATH=src $PROJECT_DIR/.venv/bin/python app.py >> $PROJECT_DIR/cron_bot.log 2>&1"

# Get current crontab for the user
CURRENT_CRON=$(crontab -u "$ACTUAL_USER" -l 2>/dev/null || echo "")

# Check if the cron job already exists
if echo "$CURRENT_CRON" | grep -Fq "$PROJECT_DIR/.venv/bin/python app.py"; then
    print_warning "Cron job already exists. Skipping to avoid duplicates."
else
    # Add the new cron job
    if [ -z "$CURRENT_CRON" ]; then
        # No existing crontab, create new one
        echo "$CRON_JOB" | crontab -u "$ACTUAL_USER" -
    else
        # Append to existing crontab
        (echo "$CURRENT_CRON"; echo "$CRON_JOB") | crontab -u "$ACTUAL_USER" -
    fi
    print_success "Cron job added successfully"
fi

# ============================================================================
# 3. Verification
# ============================================================================
print_info "Verifying setup..."

# Check service status
if systemctl is-active --quiet bfx-dashboard.service; then
    print_success "Dashboard service is active and running"
else
    print_warning "Dashboard service may not be running properly. Check with: systemctl status bfx-dashboard.service"
fi

# Display cron job
print_info "Current cron jobs for user $ACTUAL_USER:"
crontab -u "$ACTUAL_USER" -l

# ============================================================================
# 4. Final Summary
# ============================================================================
echo ""
print_success "=========================================="
print_success "Server setup completed successfully!"
print_success "=========================================="
echo ""
print_info "Dashboard Service:"
echo "  - Service name: bfx-dashboard"
echo "  - Status: $(systemctl is-active bfx-dashboard.service)"
echo "  - Management commands:"
echo "    systemctl status bfx-dashboard.service"
echo "    systemctl restart bfx-dashboard.service"
echo "    systemctl stop bfx-dashboard.service"
echo ""
print_info "Bot Cron Job:"
echo "  - Schedule: Every 5 minutes"
echo "  - Log file: $PROJECT_DIR/cron_bot.log"
echo "  - View logs: tail -f $PROJECT_DIR/cron_bot.log"
echo ""
print_info "Dashboard URL: http://localhost:8000"
echo ""
