module.exports = {
  apps: [{
    name: 'alter-bot-v2',
    script: 'bot_v2.py',
    cwd: '/home/alyssa/.openclaw/workspace/alter-bot-v1',
    max_restarts: 20,
    min_uptime: '2m',
    restart_delay: 1000,
    autorestart: true,
    watch: false,
    kill_timeout: 5000,
    env: {
      NODE_ENV: 'production',
      POLYMARKET_ADDRESS: '0xe8e932f75831c8181b7d847b29ee0cf37d3e7717',
      POLYMARKET_API_KEY: '019d7082-4e31-7063-a76d-26c4d09af42d',
      POLYMARKET_SECRET: '6QvaUmQgvc-0avIcXHROeo3Nb0H8toph5W7pjFJ-Uow=',
      POLYMARKET_PASSPHRASE: '51ab8ee2bc9fbf1a4f548f29b8ca305a26d0946341e257cdfb08aa1a21087de3'
    }
  }]
};
