#!/bin/bash

# If CRON_SCHEDULE is set, update the cron job
if [ ! -z "$CRON_SCHEDULE" ]; then
    echo "# Hudson News Bot Cron Job (Custom Schedule)" > /etc/cron.d/hudson-news-bot
    echo "$CRON_SCHEDULE root /usr/local/bin/run-hudson-bot.sh" >> /etc/cron.d/hudson-news-bot
    echo "@reboot root /usr/local/bin/run-hudson-bot.sh" >> /etc/cron.d/hudson-news-bot
    chmod 0644 /etc/cron.d/hudson-news-bot
fi

# Start cron service
service cron start

# Run once on startup
/usr/local/bin/run-hudson-bot.sh

# Tail the log file to keep container running
tail -f /var/log/hudson-news-bot.log