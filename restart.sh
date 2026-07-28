#!/bin/bash
# Перезапуск сайта после изменений кода
echo "Restarting premises-web..."
systemctl restart premises-web-flask
sleep 2
if systemctl is-active premises-web-flask >/dev/null 2>&1; then
    echo "OK — сайт работает на порту 3000"
    curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3000/login
else
    echo "ERROR — не удалось запустить"
    systemctl status premises-web-flask --no-pager
fi
