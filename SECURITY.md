# Security and Privacy

## Rules

- Run locally first.
- Do not commit `.env`, SQLite databases, Apple Health exports, or raw biometric
  files.
- Do not send raw health data to external services without explicit approval.
- Keep raw data and agent summaries separate.
- Use local API keys even on localhost.
- Treat agent output as wellness coaching, not medical advice.

## Sensitive Data

The following are considered sensitive:

- Sleep sessions
- Heart rate samples
- Weight
- Stress notes
- Health trends
- Daily activity history

## Agent Boundary

Agents may:

- Summarize habits.
- Suggest low-risk actions.
- Create reminders.
- Recommend professional help when patterns repeat.

Agents must not:

- Diagnose conditions.
- Recommend medication changes.
- Interpret acute symptoms as medical certainty.
