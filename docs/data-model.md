# Data Model

## daily_health_metrics

One row per user and metric date.

- metric_date
- steps
- distance_meters
- active_energy_kcal
- exercise_minutes
- resting_heart_rate_bpm
- average_heart_rate_bpm
- oxygen_saturation_percent

## sleep_sessions

Sleep intervals may cross midnight.

- started_at
- ended_at
- asleep_minutes
- source

## heart_rate_samples

Raw samples are optional for MVP. Agents should consume summaries first.

- sampled_at
- bpm
- source

## activity_sessions

Exercise or walking/running sessions.

- activity_type
- started_at
- ended_at
- distance_meters
- active_energy_kcal

## wellness_notes

Manual context for stress, fatigue, mood or habits.

## agent_summaries

Generated daily/weekly summaries written to workspace.

## reminders

Actionable reminders generated from rules.
