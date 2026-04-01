#!/bin/bash
# Save alter-bot-v2 learnings to Obsidian every hour

DATE=$(date +%Y-%m-%d)
OBSIDIAN_PATH="/mnt/c/Users/colbe/OneDrive/Documents/obsidian-vault/Journal"
BOT_PATH="/home/alyssa/.openclaw/workspace/alter-bot-v1"

# Get current stats
cd $BOT_PATH
python3.12 bot_v2.py status > /tmp/alter_status.txt 2>&1
python3.12 bot_v2.py accuracy > /tmp/alter_accuracy.txt 2>&1

# Append to daily learnings
echo "=== Hourly Update $(date +%H:%M) ===" >> $OBSIDIAN_PATH/${DATE}-AlterBot-V2-Hourly.md
echo "Balance: $(grep 'Balance:' /tmp/alter_status.txt | head -1)" >> $OBSIDIAN_PATH/${DATE}-AlterBot-V2-Hourly.md
echo "Open positions: $(grep 'Open:' /tmp/alter_status.txt | head -1)" >> $OBSIDIAN_PATH/${DATE}-AlterBot-V2-Hourly.md

echo "Hourly learnings saved"
