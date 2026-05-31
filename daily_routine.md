# Daily Routine & Human Constraints

These are guidelines for the scheduling AI. Treat them as intelligent defaults, but override them if the user specifies differently in their daily updates.

1. **Sleep Schedule**: The user typically wakes up around 8:00 AM and sleeps around 11:30 PM. Do not schedule tasks during sleep hours unless absolutely necessary.
2. **Meals**: The user sometimes cooks meals and sometimes doesn't. Reserve roughly 1 hour for lunch (around 1:00 PM) and 1 hour for dinner (around 8:00 PM) as buffer blocks. If the user explicitly says they don't need to cook today, you can compress or remove these blocks.
3. **Gym & Fitness**: A full gym session takes roughly 2 hours (including commute). The user has rest days. If the user doesn't mention the gym in their daily updates, assume they want a 2-hour gym block scheduled at a convenient time. If they say "rest day", skip the gym block.
4. **General Hygiene**: Leave small buffers (15-30 mins) in the morning and evening for general routine/hygiene.

**AI Instruction**: Do not pack the schedule back-to-back for 12 hours. Leave small breathing room between deep work sessions.
