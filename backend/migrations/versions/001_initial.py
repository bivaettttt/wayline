from alembic import op

revision = "001"
down_revision = None


def upgrade():
    op.execute("""
    CREATE TABLE users(login text PRIMARY KEY, name text NOT NULL, role text NOT NULL
      CHECK(role IN ('TRAVELER','OPERATIONS_ANALYST','ADMIN')), password text NOT NULL);
    CREATE TABLE sessions(digest text PRIMARY KEY, login text REFERENCES users, expires timestamptz NOT NULL);
    CREATE TABLE airports(code text PRIMARY KEY, city text NOT NULL, zone text NOT NULL, country text NOT NULL);
    CREATE TABLE airlines(code text PRIMARY KEY, name text NOT NULL);
    CREATE TABLE flights(id text PRIMARY KEY, number text NOT NULL, airline text NOT NULL REFERENCES airlines,
      origin text NOT NULL REFERENCES airports,destination text NOT NULL REFERENCES airports,
      scheduled_dep timestamptz NOT NULL,scheduled_arr timestamptz NOT NULL,
      estimated_dep timestamptz,estimated_arr timestamptz,actual_dep timestamptz,actual_arr timestamptz,
      terminal_dep text NOT NULL,terminal_arr text NOT NULL,
      status text NOT NULL DEFAULT 'SCHEDULED', revision integer NOT NULL DEFAULT 0,
      source_time timestamptz, snapshot_hash text, CHECK(scheduled_arr>scheduled_dep),CHECK(origin<>destination));
    CREATE INDEX flights_search ON flights(origin,scheduled_dep);
    CREATE TABLE feed(id bool PRIMARY KEY CHECK(id), cursor bigint NOT NULL DEFAULT 0,
       healthy bool NOT NULL DEFAULT false,last_success timestamptz,last_error text,
       generation bigint NOT NULL DEFAULT 0);
    INSERT INTO feed(id) VALUES(true);
    CREATE TABLE sync_runs(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, request uuid NOT NULL,
       start_cursor bigint NOT NULL,end_cursor bigint NOT NULL,status text NOT NULL,detail jsonb NOT NULL,
       created_at timestamptz NOT NULL DEFAULT clock_timestamp());
    CREATE TABLE events(sequence bigint PRIMARY KEY, event_id text NOT NULL, flight text,
       revision int, source_time timestamptz, received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
       disposition text NOT NULL, hash text NOT NULL, payload jsonb NOT NULL);
    CREATE INDEX event_lookup ON events(event_id,sequence);
    CREATE INDEX event_flight ON events(flight,sequence);
    CREATE TABLE policies(airport text REFERENCES airports,version int NOT NULL,domestic int NOT NULL,
       international int NOT NULL,terminal_extra int NOT NULL,author text REFERENCES users,
       created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(airport,version));
    CREATE TABLE trips(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),owner text NOT NULL REFERENCES users,
      title text NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE segments(trip uuid REFERENCES trips,position int,flight text NOT NULL REFERENCES flights,
      PRIMARY KEY(trip,position),UNIQUE(trip,flight));
    CREATE INDEX by_flight ON segments(flight,trip);
    CREATE TABLE assessments(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,trip uuid NOT NULL REFERENCES trips,
      fingerprint text NOT NULL, event_sequence bigint REFERENCES events, risk text NOT NULL,detail jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now());
    CREATE INDEX assessment_history ON assessments(trip,id);
    CREATE TABLE incidents(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),trip uuid NOT NULL REFERENCES trips,
      status text NOT NULL CHECK(status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
      reason text NOT NULL,assessment bigint NOT NULL REFERENCES assessments,
      opened_at timestamptz NOT NULL DEFAULT now(),resolved_at timestamptz);
    CREATE UNIQUE INDEX one_open_incident ON incidents(trip) WHERE resolved_at IS NULL;
    CREATE TABLE notifications(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,trip uuid NOT NULL REFERENCES trips,
      assessment bigint NOT NULL REFERENCES assessments,kind text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
      read_at timestamptz,UNIQUE(trip,assessment,kind));
    CREATE TABLE searches(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),trip uuid REFERENCES trips,
      actor text NOT NULL REFERENCES users,generation bigint NOT NULL,request uuid NOT NULL,
      inputs jsonb NOT NULL,options jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE audit(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,actor text REFERENCES users,
      request uuid NOT NULL,action text NOT NULL,subject text NOT NULL,detail jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now());
    CREATE FUNCTION append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Immutable history' USING ERRCODE='23514'; END $$;
    CREATE TRIGGER freeze_events BEFORE UPDATE OR DELETE ON events FOR EACH ROW EXECUTE FUNCTION append_only();
    CREATE TRIGGER freeze_assessments BEFORE UPDATE OR DELETE ON assessments FOR EACH ROW EXECUTE FUNCTION append_only();
    CREATE TRIGGER freeze_policies BEFORE UPDATE OR DELETE ON policies FOR EACH ROW EXECUTE FUNCTION append_only();
    CREATE TRIGGER freeze_audit BEFORE UPDATE OR DELETE ON audit FOR EACH ROW EXECUTE FUNCTION append_only();
    """)


def downgrade():
    op.execute(
        "DROP TABLE audit,searches,notifications,incidents,assessments,segments,trips,policies,events,sync_runs,feed,flights,airlines,airports,sessions,users CASCADE"
    )
    op.execute("DROP FUNCTION append_only()")
