---
id: TASK-10
title: 'Your Day: require a real attendee + show meeting title'
status: Done
assignee: []
created_date: '2026-07-09 11:59'
labels:
  - almanac
dependencies: []
priority: medium
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two fixes to the "Your Day" masthead line (almanac/calendar.py):

1. "First meeting" should only consider events with another real attendee
   - require at least one OTHER attendee (not just yourself) whose
   responseStatus is accepted or has not yet responded (i.e. exclude
   events whose only other attendees have declined, and exclude
   solo/focus-time blocks with no other attendees at all).

   Confirmed gap: the `timed` filter (calendar.py:116) only excludes
   all-day events and events YOU declined (_declined(), :127-131) - it has
   no check on other attendees presence/status at all, so solo blocks
   count as "meetings" and can become the reported first meeting.

2. Show the meeting's title instead of the generic "First mtg" label.

   Confirmed: first_title is already captured in the YourDay model
   (calendar.py:122, event.get("summary")) but the template never renders
   it - edition.html.j2:222 only shows "First mtg {{ first_time }}".

Recommended: add an attendee-status check (an attendee entry where `self`
is falsy AND responseStatus is not "declined") alongside the existing
_declined() filter, applied to BOTH the first-meeting pick and
meeting_count for consistency. Then swap the template line to lead with
first_title (truncated to fit the masthead ear if long - no truncation
helper exists yet; CSS text-overflow:ellipsis on a fixed-width span is the
simplest route) instead of "First mtg", still alongside the time.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Solo/focus-time blocks with no other attendee never count as the first meeting or toward meeting_count
- [x] #2 Events whose only other attendee(s) declined are excluded the same way
- [x] #3 Masthead line shows the meeting's title (or its truncated start) instead of 'First mtg'
- [x] #4 tests/test_calendar.py covers: solo block excluded, all-other-attendees-declined excluded, title rendered
<!-- AC:END -->
