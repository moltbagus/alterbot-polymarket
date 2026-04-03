module.exports = {
  apps: [{
    name: 'alter-bot-v2',
    script: 'bot_v2.py',
    interpreter: 'python3.12',
    cwd: '/home/alyssa/.openclaw/workspace/alter-bot-v1',
    wait_ready: false,
    idle_mode: false,
    kill_timeout: 5000,
    env: {
      PM2_IDLE_RESTART_TIMEOUT: 0
    }
  }]
};
