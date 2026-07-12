---
id: TASK-11
title: 'Weather: simplify to daily-general + rain/snow indicator icon'
status: Done
assignee: []
created_date: '2026-07-09 11:59'
updated_date: '2026-07-10 13:48'
labels:
  - almanac
  - render
dependencies: []
priority: low
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Simplify the Weather masthead ear: just current/general weather for the
day, plus a separate small icon if rain/snow is expected at any point today
- no detailed precipitation timing/amount needed.

Confirmed current behavior: weather.py fetches INSTANTANEOUS
current.weather_code for the main icon/condition plus
daily.temperature_2m_max/min, and the masthead renders temp + H/L +
condition text (edition.html.j2:199-206). The instant code can mismatch
"the day" as a whole (e.g. clear at 6am, rain by afternoon), and the line
is more text than wanted.

Recommended direction:
- Switch the primary icon/condition to Open-Meteo's daily.weather_code
  (the day's representative condition) instead of the instantaneous one.
- Add daily.precipitation_probability_max (or rain_sum/snowfall_sum) to
  decide whether to show a small secondary rain-cloud/flurries icon
  (render/icons.py already has "rain" and "snow" icon glyphs to reuse).
- Trim the masthead line to drop unwanted detail - exact trim (keep temp?
  drop H/L text?) left to implementation, but the end state should read as
  "general weather for the day" plus optional precip icon, not a detailed
  forecast.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Main icon/condition reflects the day's general conditions, not just the instant reading
- [ ] #2 A small secondary rain-cloud or flurries icon appears only when precipitation is expected today
- [ ] #3 No detailed precipitation amount/timing text added - icon only
- [ ] #4 Masthead ear line is shorter/simpler than today
<!-- AC:END -->
