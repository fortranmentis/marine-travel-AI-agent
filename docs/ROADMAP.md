# Implementation roadmap

## v0.1 — implemented prototype

- [x] Credential-file parsing without executing document contents
- [x] Public API checks and fully paginated collection
- [x] Atomic snapshots and partial-fetch rejection
- [x] Regional candidates, time windows, fixed bookings and exclusions
- [x] Bounded Ollama tools and rule-based fallback
- [x] Korean UI, place map links and provenance
- [x] Offline regression tests and CI configuration

## Next: verify family travel feasibility

1. Review operators, minimum ages, operating hours, booking requirements, facilities
   and authoritative associations between activity venues and forecast sites.
2. Add road/bridge/ferry accessibility classification and real route travel times.
3. Integrate warning bulletins and access restrictions.
4. Interpret operating calendars and verify indoor alternatives.
5. Add lodging, arrival/departure and first/last-day constraints.
6. Compare feasible dates by activity suitability, movement and preferences.
7. Evaluate Korean tool accuracy, reservation preservation, prose grounding and load
   using a fixed, larger evaluation set.

## Later

- PostGIS, scheduled collection and source-specific freshness policies
- Ferry schedules and cancellation handling
- Forecast-change comparison and user-controlled replanning
- Tourism images with attribution and license checks
- Authentication, deployment and operational monitoring

No bookings, payments or operator messages are performed.
