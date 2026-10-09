# Agent ideas (reference notes)

## Why this file exists
Owner (Huseyin, math student, learning SQL) watched a video about running an "agent company" with Claude Code.
Notes below are reference material, NOT a to-do list. Nothing here is approved for building unless the owner says
so in a new message.

## Owner constraints (always apply)
- Token/limit budget is tight. Prefer the PyCharm agent for all work. Do not suggest paid upgrades.
- Explain in plain Turkish; put the Turkish meaning in parentheses next to every English term.
- Owner learns from worked examples, not abstract text. One concrete step at a time.
- Code, variable names, commit messages and new docs are in English.
- Never commit/push without explicit approval. Never put secrets in git.
- Possible future direction after Panosu: game development (player behaviour analysis, drop rates, game balance,
  churn). Math/probability background is the owner's edge.

## Video summary (agent company idea)
1. Four things an agent needs: desk (memory files), job description (CLAUDE.md + skills), keys (API keys/MCP in
   .env, never in git), shift (a schedule/loop so it works while the owner is away).
2. Outer loop = scheduled runs (e.g. daily 09:00). Inner loop = one run: call tool, read result, think, write
   output.
3. File layout: constitution (rules every agent reads first; agents may not edit it), per-team rules, agent file
   (name, model, tools, keys, schedule, budget), notebook ("defter"): after each run the agent writes ONE short
   lesson; weekly the notebook is distilled into rules and then cleared.
4. Agents do not message each other; they read each other's status/notebook files.
5. Token discipline: each agent reads only its own few files, cheaper model for simple jobs, no run when there is
   no work.
6. Start small (3 agents, not 13). Tool choice does not matter, architecture does. Never publish to social
   accounts without human approval.
7. The demo also used a Telegram bot, Apify scraping, fal image generation, Obsidian and a dispatcher. Not needed
   for Panosu now.

## Decision for Panosu (as of 2026-10-09)
- Adopt nothing yet. Candidate ideas, only if the owner asks: (a) a short lessons notebook file (docs/lessons.md,
  one line per finished task, cleared weekly into CLAUDE.md rules), (b) one scheduled health check of the live
  site/demo refresh.
- Skip: multiple agents, Telegram, Apify, image generation, always-on listener (extra cost and upkeep, no help for
  the first pilot firm).
- Revisit when the owner starts a game project: a small agent team (task list, bug log, balance tuning) could fit
  there.
