# Verification / Проверки

| Requirement | Rule and component | Verification |
| --- | --- | --- |
| FR-01 | Trip ownership and ordered legs in [trip service](../backend/wayline/trips.py) | TC-01. Foreign object returns 404. UI saves a valid two-leg itinerary |
| FR-02 | Zoned display and UTC arithmetic in [domain](../backend/wayline/domain.py) | TC-02. Gap/fold DST, overnight arrival, date line and immutable schedule |
| FR-03 | Durable checkpoint in [integration](../backend/wayline/integration.py) | TC-03. HTTP failures, timeouts, invalid payload, retry after failed PostgreSQL write |
| FR-04 | Revision and idempotency in [integration](../backend/wayline/integration.py) | TC-04. Duplicate, stale, conflict, gap and concurrent polling |
| FR-05 | Synthetic MCT and freshness in [domain](../backend/wayline/domain.py) | TC-05. 95→35 minute erosion, rule publication, DST rejection, repeated recalculation |
| FR-06 | Feasible search in [domain](../backend/wayline/domain.py) | TC-06. Cancelled leg excluded, infeasible transfer rejected, snapshot invalidated |
| FR-07 | Incident and in-app notification in [trip service](../backend/wayline/trips.py) | TC-07. One active incident, acknowledgment, closing assessment and read status |
| FR-08 | [Lab implementation](../backend/wayline/lab.py) and [launcher](../scripts/lab) | TC-08. Actual HTTP requests on separate volumes and role restrictions |

[Unit cases](../tests/test_domain.py) · [HTTP and PostgreSQL verification](../scripts/verify.py) · [Browser flow](../frontend/e2e/wayline.spec.ts)

```sh
python -m pip install -r requirements.txt pytest ruff
ruff check backend provider scripts tests
ruff format --check backend provider scripts tests
pytest -q
PYTHONPATH=.:backend python scripts/contracts.py
scripts/lab up
cd frontend
npm ci
npx playwright install chromium
npm run e2e
cd ..
docker compose -p wayline-lab exec -T api python -u - < scripts/verify.py
```

Run browser and integration suites sequentially against the lab. Some cases change a simulated flight permanently. Use `scripts/lab reset` to recreate the lab database and provider feed.
