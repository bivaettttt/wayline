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

## Actors and use cases

| Participant | Need | Use case |
| --- | --- | --- |
| Traveler | Know if an existing itinerary is workable | UC-01. Save occurrences in travel order, read own assessment, compare suggestions and acknowledge a disruption |
| Operations analyst | Explain projection changes | UC-02. Inspect provider status, feed cursor, event payload/version and disposition. Synchronize again from the saved cursor |
| Administrator | Maintain reproducibility | UC-03. Manage demo users, publish a new synthetic MCT and run experiments in the isolated deployment |

NFR-01 requires atomic progress through the provider feed. NFR-02 requires object-scoped access and chronological evidence. NFR-03 requires MCT version traceability. NFR-04 requires independent reset of the lab. BR-05 rejects revisiting airports, requires each candidate flight to be usable, and enforces one- to three-leg search with a 1–72-hour horizon. Up to five options are retained per search. A one-minute reduction is visible in assessments even if the incident reason remains unchanged.

## Decision matrix

| Input | Flight projection | Trip effect |
| --- | --- | --- |
| Event ID and normalized body repeat | Keep projection | No duplicate recalculation |
| Same event ID with another body | Record ID conflict | Keep previous assessment |
| Lower revision | Append stale disposition | Keep previous assessment |
| Same revision, different flight data | Record revision conflict | Keep previous assessment |
| Higher revision fights terminal or actual facts | Record rejected transition | Keep previous assessment |
| Higher valid revision | Apply with gap/late reason where relevant | Reassess linked trips |
| Timeout or invalid envelope | Keep forecast, mark feed unavailable | UNKNOWN where affected by unconfirmed information |
| Recovery | Poll retained checkpoint | Reassess freshness and resolve applicable incident |

Effective time uses actual, then estimated, then scheduled. International MCT applies if either leg is international. Different terminals add the rule's margin. On an already-started journey, completed segments determine the known airport and the inbound leg participates in the first candidate connection check.

## Data dictionary and policy

A flight occurrence is a dated instance of a synthetic flight number. A source event has an identity and a flight revision. Delivery sequence is a separate feed position. A trip contains ordered references to occurrences. An assessment freezes the effective gaps, applicable rule versions and flight revisions. An incident tracks acknowledgment and resolution. A search records the schedule generation, constraints and suggestions. A notification is an in-app message derived from an incident change.

Travelers can read the shared synthetic catalogue and operate on their own trips, notifications and searches. Operations analysts read shared trip diagnostics and synchronize the provider. Administrators additionally create users, publish MCT and run permitted lab scenarios. Password hashes and session digests remain server-side. The API binds callbacks to a fixed provider hostname and exposes no arbitrary destinations. External traffic, commercial GDS, passenger identities and public deployment are excluded.

[Context](diagrams/context.mmd) · [Containers](diagrams/containers.mmd) · [ERD](diagrams/data.mmd) · [Polling sequence](diagrams/poll.mmd) · [Incident states](diagrams/incident.mmd) · [Traceability](verification.md)
