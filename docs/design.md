# Wayline · Analysis and architecture

Travelers need an explanation when a change to one flight affects the rest of their journey. Operations analysts need the evidence for every accepted, stale and conflicting update. Administrators maintain synthetic connection rules and control isolated simulations.

| Requirement | Acceptance |
| --- | --- |
| FR-01 Trip | The traveler saves connected ordered occurrences and reads only their own itinerary |
| FR-02 Time | Schedule, estimate and actual are separate UTC instants. Display converts each end to its airport's IANA zone |
| FR-03 Integration | An independent provider exposes schedule and a durable sequence feed. A bounded HTTP poll advances its cursor only in the transaction that handles its entries |
| FR-04 Projection | Per-flight revision controls freshness. Duplicate ID, same-revision differences, invalid transitions and gaps leave audit evidence |
| FR-05 Connection | Effective times and a versioned airport MCT explain the available interval and risk |
| FR-06 Alternatives | Search over dated occurrences excludes impossible legs and freezes data from one database snapshot |
| FR-07 Incident | At most one active incident per trip. Assessments and notifications explain changes. The traveler can acknowledge |
| FR-08 Operations | Authorized staff monitor polling outcomes and event disposition. The isolated lab can exercise failures |

**ADR-01.** PostgreSQL stores absolute instants as timestamptz. Local input with ambiguous or missing wall times requires explicit handling. Provider payloads use offset timestamps. Browser Intl converts by IANA zone.

**ADR-02.** Use one authoritative synthetic provider. A separate SQLite service supplies an append-only delivery sequence, independent from the application's PostgreSQL flight revision. This avoids dependence on clock order. Each update is a full forecast snapshot. Gaps apply with a recorded reason. A higher revision can correct forecasts; terminal and actual facts are protected.

**ADR-03.** Provider HTTP runs before the application transaction. The transaction locks a single feed checkpoint and advances only if the cursor matches the fetched base. It records dispositions, updates the flight and recalculates affected trips atomically. HTTP failures retain the previous checkpoint and mark information unavailable. Retry is the next poll with the same cursor.

**ADR-04.** Route search uses a bounded traversal of dated flight legs in a repeatable PostgreSQL snapshot. Constraints cover elapsed time, connection airport and local rules, route cycles, cancellation, freshness and maximum legs. Rank by arrival, legs, duration and stable occurrence IDs. No booking is performed.

**ADR-05.** Risk and operational status are different. Delay is derived from estimated or actual versus scheduled instants. Trip risk evolves independently from acknowledgment. Recovery resolves an existing incident. Semantic repetitions do not duplicate notices.

| Business rule | Result |
| --- | --- |
| BR-01 | Exact ID replay is ignored. Changed content with the same ID is a conflict |
| BR-02 | Lower revisions are stale, same revision with different payload conflicts, higher valid revisions apply |
| BR-03 | Connection layover below zero is MISSED, below MCT is AT_RISK, otherwise SAFE. Unavailable data or policy gives UNKNOWN |
| BR-04 | Policy is per airport. International connections use a distinct time. Different terminals add a margin |
| BR-05 | Alternatives exclude canceled and diverted flights and only used airport paths are expanded |
| BR-06 | Missing provider data is explicit even when last known estimates are retained |
