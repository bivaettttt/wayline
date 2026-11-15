# Wayline status / Состояние проекта

The working educational release connects an independent synthetic provider to a PostgreSQL-backed itinerary and connection analysis workspace. The normal and isolated Lab deployments have separate data volumes.

## Known limitations

- The timetable uses the provider volume's anchor date. Application startup imports newly listed occurrences and preserves existing schedules. It does not roll indefinitely. A fresh isolated lab anchors the timetable to the next UTC day.
- One synthetic provider is authoritative. Multiple-source reconciliation, commercial flight feeds, availability and booking are outside this release.
- Provider events update operational status, estimates, actual times and terminals. Timetable replacements are new occurrences, and the demo simulator does not expose a recurring schedule management UI.
- Alternative recommendations use structured elapsed-time and MCT checks. Search generation invalidates retained results after a projection change. The lab verifies invalidation across a completed search and subsequent update.
- A cancellation is terminal and stays recorded. The cancellation scenario uses its own inbound occurrence. A reset restores all lab inputs.
- In-app messages cover changes of disruption reason and recovery. An external delivery service and distinct alerts for every same-severity estimate or search result are pending.
- Global provider/audit diagnostic data is available to staff. Provider settings are managed through Compose. Dedicated source administration and audit screens remain outside the current UI.
- OpenAPI is generated from the running services. Some response schemas are generic objects.

## Verification record

Local execution passed ten unit cases, the PostgreSQL HTTP integration suite, 23 lab experiments and two Chromium tests. HTTP checks use the independent simulator and real PostgreSQL. Captures and videos are from browser tests. [How to reproduce](verification.md) · [Current GitHub Actions](https://github.com/bivaettttt/wayline/actions)
