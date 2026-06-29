#!/bin/bash
PROJECT_DIR="/home/wayne.chiu/bitfinex-lending-bot"
APP_USER="wayne.chiu"

echo -e "\e[34m[1/3] 準備部署 Dashboard 背景服務...\e[0m"

SERVICE_FILE="/etc/systemd/system/bfx-dashboard.service"
sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Bitfinex Lending Bot Dashboard API
After=network.target

[Service]
User=$APP_USER
WorkingDirectory=$PROJECT_DIR
Environment="PYTHONPATH=src"
ExecStart=$PROJECT_DIR/.venv/bin/uvicorn bitfinex_lending_bot.dashboard_api:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable bfx-dashboard
sudo systemctl start bfx-dashboard
echo -e "\e[32m✅ Dashboard 服務已啟動並設定開機自動重啟！\e[0m"

echo -e "\e[34m[2/3] 準備設定機器人自動排程...\e[0m"

BOT_SERVICE_FILE="/etc/systemd/system/bfx-bot.service"
sudo tee $BOT_SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Bitfinex Lending Bot
After=network.target

[Service]
User=$APP_USER
WorkingDirectory=$PROJECT_DIR
Environment="PYTHONPATH=src"
ExecStart=$PROJECT_DIR/.venv/bin/python app.py
StandardOutput=append:$PROJECT_DIR/cron_bot.log
StandardError=append:$PROJECT_DIR/cron_bot.log

[Install]
WantedBy=multi-user.target
EOF

BOT_TIMER_FILE="/etc/systemd/system/bfx-bot.timer"
sudo tee $BOT_TIMER_FILE > /dev/null <<EOF
[Unit]
Description=Run Bitfinex Lending Bot every 5 minutes

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable bfx-bot.timer
sudo systemctl start bfx-bot.timer
echo -e "\e[32m✅ 機器人每 5 分鐘自動執行已設定完成（使用 systemd timer）！\e[0m"

echo -e "\e[35m[3/3] 🎉 系統全自動化部署大功告成！\e[0m"
