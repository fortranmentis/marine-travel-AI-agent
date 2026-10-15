# Implementation roadmap

## v0.1 — implemented prototype

- [x] Credential-file parsing without executing document contents
- [x] Public API checks and fully paginated collection
- [x] Atomic snapshots and partial-fetch rejection
- [x] Regional candidates, time windows, fixed bookings and exclusions
- [x] Bounded Ollama tools and rule-based fallback
- [x] Korean UI, place map links and provenance
- [x] Offline regression tests and CI configuration

## v0.2 — visual planning and targeted changes

- [x] NDJSON work-status stream, progress modal, elapsed time and recovery choices
- [x] Leaflet/OSM day maps, OSRM road routes and schedule-gap warnings
- [x] Exact-ID tourism photos, license links, seven-day metadata cache
- [x] Weather SVG icons, trip-hour summary and expandable hourly cards
- [x] Revisioned single-slot replacement, undo, location-preserving lock/unlock
- [x] Bounded two-hour plan registry and one-request-per-second routing

## v0.3 — preferences and transport readiness

- [x] Solo/couple/family/group, child count and per-child ages
- [x] Per-day hours and requested attraction/experience counts
- [x] Nearby TourAPI meals by source cuisine and optional cafe breaks
- [x] Foot-graph routing, mode-specific route checks and map labels
- [x] Daily and whole-trip sea-travel outlooks with missing-coverage handling
- [x] Weather arrow controls, mouse dragging, touch and keyboard scrolling
- [x] ODsay adapter and KOMSA raw-schedule collector (keys not yet configured)
- [x] Reviewed, expiring passenger-ferry day-trip scheduler and cancellation guards
- [ ] Live transit/ferry validation and first real reviewed island
- [ ] Overnight island stays, vehicle shipping and verified island food

## Next: verify family travel feasibility

1. Review operators, minimum ages, operating hours, booking requirements, facilities
   and authoritative associations between activity venues and forecast sites.
2. Review road/bridge/ferry accessibility, parking access and traffic-aware route times.
3. Integrate warning bulletins and access restrictions.
4. Interpret operating calendars and verify indoor alternatives.
5. Add lodging, arrival/departure and first/last-day constraints.
6. Compare feasible dates by activity suitability, movement and preferences.
7. Evaluate Korean tool accuracy, reservation preservation, prose grounding and load
   using a fixed, larger evaluation set.

## Later

- PostGIS, scheduled collection and source-specific freshness policies
- Live ferry cancellations and operator/arrival-time reconciliation
- Forecast-change comparison and user-controlled replanning
- Broader image availability and verified operator-specific photo associations
- Authentication, deployment and operational monitoring

No bookings, payments or operator messages are performed.
