# Alter-Bot Coding Prompt Templates

## Vibe Coding Prompt (GPT-5.5 style, adapted for alter-bot)

Use this template when requesting Turing/hermes to build new alter-bot features:

```
You are a senior full-stack engineer + product designer. Build me a production-grade [FEATURE TYPE] end-to-end.

Goal: [ONE-LINE OUTCOME — what the feature accomplishes]
Users: [who uses this + their main pain point]
Core features: [3-5 must-haves, in priority order]
Stack: Python, Polymarket API, pm2, state.json
Aesthetic: [reference existing alter-bot code style + patterns]
Before writing code: plan the architecture, list assumptions, ask me anything ambiguous. Then build it in full. Use real data structures, real components, real states (loading/empty/error). No placeholders, no TODOs. Make it look like it was built by a senior quant dev.
```

## Power Add-Ons (append as needed)
- "Add proper error handling, circuit breakers, and state persistence"
- "Make it backwards-compatible with existing state.json schema"
- "When done, self-review and fix anything below production quality"
- "Run pyflakes or pylint before claiming done"

## 6 Variables for Alter-Bot Features
1. Feature type — signal generator, resolver, position manager, monitor
2. Goal — single outcome
3. Users + pain point
4. Features — 3-5 prioritized
5. Stack — Python, requests, pm2, state.json
6. Aesthetic refs — existing bot_v2.py patterns

## Why This Works for Alter-Bot
- Forces a plan before code
- Names the role (senior quant dev + engineer)
- Demands real states, not mockups
- Closes ambiguity loops upfront
- Production-grade bar from day one
