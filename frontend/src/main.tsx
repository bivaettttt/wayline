import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "./style.css";
import { useState, type FormEvent, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  HashRouter,
  Link,
  NavLink,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Activity,
  Bell,
  CalendarDays,
  Compass,
  FlaskConical,
  GitBranch,
  LogOut,
  Plane,
  Radar,
  Settings2,
  UsersRound,
  TriangleAlert,
} from "lucide-react";
import {
  api,
  setToken,
  type Airport,
  type Assessment,
  type Connection,
  type Event,
  type Flight,
  type Notice,
  type Operations,
  type Policy,
  type Search,
  type Trip,
  type User,
} from "./api";

const names: Record<string, string> = {
  SAFE: "Пересадка доступна",
  AT_RISK: "Пересадка под угрозой",
  MISSED: "Маршрут нарушен",
  UNKNOWN: "Данные недоступны",
  SCHEDULED: "По расписанию",
  CHECK_IN: "Регистрация",
  BOARDING: "Посадка",
  DEPARTED: "Вылетел",
  IN_AIR: "В воздухе",
  LANDED: "Приземлился",
  ARRIVED: "Прибыл",
  CANCELLED: "Отменён",
  DIVERTED: "Перенаправлен",
  OPEN: "Открыто",
  ACKNOWLEDGED: "Принято к сведению",
  RESOLVED: "Восстановлено",
  FLIGHT_DELAYED: "Задержка рейса",
  FLIGHT_DISRUPTED: "Отмена или перенаправление",
  CONNECTION_AT_RISK: "Недостаточный запас пересадки",
  MISSED_CONNECTION: "Пересадка пропущена",
  PROVIDER_UNAVAILABLE: "Источник недоступен",
  ALTERNATIVES_AVAILABLE: "Подходящие варианты найдены",
  NO_FEASIBLE_ALTERNATIVE: "Допустимых маршрутов нет",
  DATA_UNAVAILABLE: "Нет актуального расписания",
  TRAVELER: "Путешественник",
  OPERATIONS_ANALYST: "Операционный аналитик",
  ADMIN: "Администратор",
};
const name = (s: string) => names[s] ?? s;
const stamp = (value: string | null, zone = "UTC") =>
  value
    ? new Intl.DateTimeFormat("ru", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: zone,
        timeZoneName: "short",
      }).format(new Date(value))
    : "—";
const form = (event: FormEvent<HTMLFormElement>) => {
  event.preventDefault();
  return Object.fromEntries(new FormData(event.currentTarget));
};
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 5000 } },
});
function useData<T>(path: string, enabled = true) {
  return useQuery({ queryKey: [path], queryFn: () => api<T>(path), enabled });
}
function useAction<T>() {
  const query = useQueryClient();
  return useMutation({
    mutationFn: ({ path, data }: { path: string; data?: unknown }) =>
      api<T>(path, "POST", data),
    onSuccess: () => query.invalidateQueries(),
  });
}
function ErrorView({ error }: { error?: Error | null }) {
  return error ? (
    <p className="error" role="alert">
      {error.message}
    </p>
  ) : null;
}
function Loading() {
  return (
    <p className="pad muted" role="status">
      Загрузка…
    </p>
  );
}
function Badge({ value }: { value: string }) {
  return <span className={"badge " + value.toLowerCase()}>{name(value)}</span>;
}
function Head({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children?: ReactNode;
}) {
  return (
    <header className="headline">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {children}
    </header>
  );
}
function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
function Table({
  columns,
  rows,
  empty = "Записей пока нет.",
}: {
  columns: string[];
  rows: ReactNode[][];
  empty?: string;
}) {
  return rows.length ? (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((v, j) => (
                <td key={j}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="pad muted">{empty}</p>
  );
}
function Json({ data }: { data: unknown }) {
  return <pre>{JSON.stringify(data, null, 2)}</pre>;
}
function Brand() {
  return (
    <div className="brand">
      <span>
        <Plane size={22} />
      </span>
      Wayline
    </div>
  );
}
function Login({ done }: { done: (u: User) => void }) {
  const action = useMutation({
    mutationFn: (data: unknown) =>
      api<User & { token: string }>("/auth/login", "POST", data),
    onSuccess: (u) => {
      setToken(u.token);
      done(u);
    },
  });
  return (
    <div className="login">
      <section>
        <Brand />
        <h1>Вход в Wayline</h1>
        <p>Поездки, рейсы и пересадки</p>
        <form className="form" onSubmit={(e) => action.mutate(form(e))}>
          <label>
            Логин
            <input name="login" required autoComplete="username" />
          </label>
          <label>
            Пароль
            <input
              name="password"
              required
              type="password"
              autoComplete="current-password"
            />
          </label>
          <ErrorView error={action.error} />
          <button className="primary" disabled={action.isPending}>
            Войти
          </button>
        </form>
      </section>
      <div className="login-side">
        <Compass size={48} />
        <h2>Маршрут под наблюдением</h2>
        <p>
          Следите за рейсами, оценивайте запас на пересадку и сравнивайте
          варианты на синтетическом расписании.
        </p>
      </div>
    </div>
  );
}
function App() {
  const [user, setUser] = useState<User | null>(null);
  if (!user) return <Login done={setUser} />;
  return (
    <Workspace
      user={user}
      logout={() => {
        setToken("");
        queryClient.clear();
        setUser(null);
      }}
    />
  );
}
function Workspace({ user, logout }: { user: User; logout: () => void }) {
  const ops = user.role !== "TRAVELER";
  const lab = useData<{ enabled: boolean; scenarios: Record<string, string> }>(
    "/lab",
    user.role === "ADMIN",
  );
  const items = [
    { path: "/", label: "Обзор", Icon: Compass },
    { path: "/trips", label: "Поездки", Icon: CalendarDays },
    { path: "/flights", label: "Рейсы", Icon: Plane },
    { path: "/routes", label: "Планирование", Icon: GitBranch },
    { path: "/disruptions", label: "Нарушения", Icon: TriangleAlert },
    { path: "/notifications", label: "Уведомления", Icon: Bell },
    ...(ops
      ? [
          { path: "/operations", label: "Провайдер", Icon: Radar },
          { path: "/events", label: "События", Icon: Activity },
        ]
      : []),
    ...(user.role === "ADMIN"
      ? [
          { path: "/policies", label: "Правила MCT", Icon: Settings2 },
          { path: "/users", label: "Пользователи", Icon: UsersRound },
        ]
      : []),
    ...(lab.data?.enabled
      ? [{ path: "/lab", label: "Лаборатория", Icon: FlaskConical }]
      : []),
  ];
  return (
    <div className="shell">
      <aside>
        <Brand />
        <nav aria-label="Разделы">
          {items.map(({ path, label, Icon }) => (
            <NavLink end={path === "/"} key={path} to={path}>
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>
        <footer>Синтетическое расписание</footer>
      </aside>
      <div className="workspace">
        <div className="top">
          <span>Рабочая область / Авиация</span>
          <div>
            <b>{user.name}</b>
            <span>{name(user.role)}</span>
            <button
              aria-label="Выйти"
              onClick={() => void api("/auth/logout", "POST").finally(logout)}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
        <main>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/trips" element={<Trips canCreate={!ops} />} />
            {!ops && <Route path="/trips/new" element={<Builder />} />}
            <Route path="/trips/:id" element={<TripPage traveler={!ops} />} />
            <Route path="/flights" element={<Flights />} />
            <Route path="/flights/:id" element={<FlightPage />} />
            <Route path="/routes" element={<Planner />} />
            <Route path="/disruptions" element={<Disruptions />} />
            <Route path="/notifications" element={<Notifications />} />
            {ops && (
              <>
                <Route path="/operations" element={<Provider />} />
                <Route path="/events" element={<Explorer />} />
              </>
            )}
            {user.role === "ADMIN" && (
              <>
                <Route path="/policies" element={<Policies />} />
                <Route path="/users" element={<Users />} />
              </>
            )}
            {lab.data?.enabled && (
              <Route
                path="/lab"
                element={<Lab scenarios={lab.data.scenarios} />}
              />
            )}
            <Route path="*" element={<Head title="Раздел недоступен" />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
function TripTable({ data }: { data: Trip[] }) {
  return (
    <Table
      columns={["Поездка", "Владелец", "Состояние пересадки"]}
      rows={data.map((t) => [
        <Link to={"/trips/" + t.id}>{t.title}</Link>,
        t.owner,
        <Badge value={t.risk} />,
      ])}
    />
  );
}
function Dashboard() {
  const t = useData<Trip[]>("/trips"),
    n = useData<Notice[]>("/notifications");
  return (
    <>
      <Head
        title="Обзор поездок"
        sub="Расписание, доступность пересадок и последние изменения"
      />
      <ErrorView error={t.error ?? n.error} />
      <div className="metrics">
        {[
          ["Поездки", t.data?.length],
          ["Требуют внимания", t.data?.filter((t) => t.disrupted).length],
          ["Новые уведомления", n.data?.filter((n) => !n.read_at).length],
        ].map(([label, value]) => (
          <section key={label}>
            <span>{label}</span>
            <strong>{value ?? "—"}</strong>
          </section>
        ))}
      </div>
      <Panel title="Поездки">
        {t.data ? (
          <TripTable data={t.data.slice(0, 8)} />
        ) : (
          !t.error && <Loading />
        )}
      </Panel>
      <Panel title="Недавние изменения">
        <Table
          columns={["Поездка", "Изменение", "Время UTC"]}
          rows={(n.data ?? [])
            .slice(0, 8)
            .map((x) => [
              <Link to={"/trips/" + x.trip}>{x.title}</Link>,
              name(x.kind),
              stamp(x.created_at),
            ])}
        />
      </Panel>
    </>
  );
}
function Trips({ canCreate }: { canCreate: boolean }) {
  const [offset, set] = useState(0);
  const q = useData<Trip[]>("/trips?offset=" + offset);
  return (
    <>
      <Head title="Поездки" sub="Сохранённые маршруты и состояние пересадок">
        {canCreate && (
          <Link className="button primary" to="/trips/new">
            Создать поездку
          </Link>
        )}
      </Head>
      <ErrorView error={q.error} />
      <Panel title="Реестр поездок">
        {q.data ? (
          <>
            <TripTable data={q.data} />
            <Pager offset={offset} count={q.data.length} set={set} />
          </>
        ) : (
          !q.error && <Loading />
        )}
      </Panel>
    </>
  );
}
function Pager({
  offset,
  count,
  set,
}: {
  offset: number;
  count: number;
  set: (n: number) => void;
}) {
  return (
    <div className="toolbar pad">
      <button disabled={!offset} onClick={() => set(offset - 50)}>
        Назад
      </button>
      <span className="muted">Страница {offset / 50 + 1}</span>
      <button disabled={count < 50} onClick={() => set(offset + 50)}>
        Далее
      </button>
    </div>
  );
}
function Builder() {
  const q = useData<Flight[]>("/flights");
  const act = useAction<Trip>();
  const [count, set] = useState(2);
  const navigate = useNavigate();
  return (
    <>
      <Head
        title="Новая поездка"
        sub="Выберите рейсы в порядке прохождения маршрута"
      />
      <Panel title="Сегменты маршрута">
        <form
          className="pad form"
          onSubmit={(e) => {
            const f = form(e);
            act.mutate(
              {
                path: "/trips",
                data: {
                  title: f.title,
                  flights: Array.from(
                    { length: count },
                    (_, i) => f["leg" + i],
                  ),
                },
              },
              { onSuccess: (t) => navigate("/trips/" + t.id) },
            );
          }}
        >
          <label>
            Название поездки
            <input
              name="title"
              required
              minLength={2}
              placeholder="Например, Новосибирск — Рим"
            />
          </label>
          {Array.from({ length: count }, (_, i) => (
            <label key={i}>
              Сегмент {i + 1}
              <select name={"leg" + i} required defaultValue="">
                <option value="">Выберите рейс</option>
                {q.data?.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.number} · {f.origin} → {f.destination} ·{" "}
                    {stamp(f.scheduled_dep, f.origin_zone)}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <div className="toolbar">
            <button
              type="button"
              disabled={count >= 4}
              onClick={() => set((n) => n + 1)}
            >
              Добавить сегмент
            </button>
            <button
              type="button"
              disabled={count <= 1}
              onClick={() => set((n) => n - 1)}
            >
              Убрать последний
            </button>
          </div>
          <ErrorView error={act.error ?? q.error} />
          <button className="primary" disabled={act.isPending || !q.data}>
            Сохранить поездку
          </button>
        </form>
      </Panel>
    </>
  );
}
function FlightTable({ data }: { data: Flight[] }) {
  return (
    <Table
      columns={[
        "Рейс",
        "Маршрут",
        "Плановый вылет",
        "Плановое прибытие",
        "Состояние",
      ]}
      rows={data.map((f) => [
        <Link to={"/flights/" + f.id}>{f.number}</Link>,
        f.origin + " → " + f.destination,
        stamp(f.scheduled_dep, f.origin_zone),
        stamp(f.scheduled_arr, f.destination_zone),
        <Badge value={f.status} />,
      ])}
    />
  );
}
function Flights() {
  const [offset, set] = useState(0),
    [q, filter] = useState("");
  const f = useData<Flight[]>(
    "/flights?offset=" + offset + "&q=" + encodeURIComponent(q),
  );
  return (
    <>
      <Head
        title="Рейсы"
        sub="Синтетические рейсы и локальное время аэропортов"
      />
      <Panel title="Расписание">
        <form
          className="toolbar pad"
          onSubmit={(e) => {
            const v = form(e);
            set(0);
            filter(String(v.q));
          }}
        >
          <label>
            Рейс или аэропорт
            <input name="q" />
          </label>
          <button>Найти</button>
        </form>
        <ErrorView error={f.error} />
        {f.data ? (
          <>
            <FlightTable data={f.data} />
            <Pager offset={offset} count={f.data.length} set={set} />
          </>
        ) : (
          !f.error && <Loading />
        )}
      </Panel>
    </>
  );
}
function FlightTimes({ f }: { f: Flight }) {
  return (
    <Table
      columns={["Время", "Вылет · " + f.origin, "Прибытие · " + f.destination]}
      rows={[
        [
          "План",
          stamp(f.scheduled_dep, f.origin_zone),
          stamp(f.scheduled_arr, f.destination_zone),
        ],
        [
          "Прогноз",
          stamp(f.estimated_dep, f.origin_zone),
          stamp(f.estimated_arr, f.destination_zone),
        ],
        [
          "Факт",
          stamp(f.actual_dep, f.origin_zone),
          stamp(f.actual_arr, f.destination_zone),
        ],
        ["Терминал", f.terminal_dep, f.terminal_arr],
      ]}
    />
  );
}
function EventTable({ events }: { events: Event[] }) {
  return (
    <Table
      columns={[
        "Очередь",
        "Рейс",
        "Версия",
        "Результат",
        "Время источника UTC",
        "Payload",
      ]}
      rows={events.map((e) => [
        e.sequence,
        e.flight ? <Link to={"/flights/" + e.flight}>{e.flight}</Link> : "—",
        e.revision,
        e.disposition,
        stamp(e.source_time),
        <details>
          <summary>{e.event_id.slice(0, 12)}</summary>
          <Json data={e.payload} />
        </details>,
      ])}
    />
  );
}
function FlightPage() {
  const { id } = useParams();
  const q = useData<Flight>("/flights/" + id);
  if (!q.data) return q.error ? <ErrorView error={q.error} /> : <Loading />;
  const f = q.data;
  return (
    <>
      <Link to="/flights">← Рейсы</Link>
      <Head
        title={"Рейс " + f.number}
        sub={
          f.origin_city + " → " + f.destination_city + " · версия " + f.revision
        }
      >
        <Badge value={f.status} />
      </Head>
      <Panel title="План, прогноз и факт">
        <FlightTimes f={f} />
      </Panel>
      <Panel title="История рейса">
        <EventTable events={f.events ?? []} />
      </Panel>
    </>
  );
}
function Connections({ data }: { data: Connection[] }) {
  return (
    <Table
      empty="В маршруте нет пересадок."
      columns={["Аэропорт", "План", "Доступно", "MCT", "Версия", "Оценка"]}
      rows={data.map((c) => [
        c.airport + (c.terminal_change ? " · смена терминала" : ""),
        c.planned_minutes + " мин",
        c.available_minutes + " мин",
        c.minimum_minutes === null ? "—" : c.minimum_minutes + " мин",
        c.policy_version ?? "—",
        <Badge value={c.risk} />,
      ])}
    />
  );
}
function SearchResults({ result }: { result: Search }) {
  const freshness = useData<Search>("/searches/" + result.id);
  return (
    <Panel title="Сравнение маршрутов">
      <p className="pad muted">
        Синтетическое расписание. Маршрутная рекомендация не подтверждает
        наличие мест или перебронирование.
      </p>
      <p className="toolbar pad">
        <Badge value={result.status} />
        <span>Снимок {result.generation}</span>
        {freshness.data?.current === false && (
          <span className="error">
            Расписание изменилось. Выполните новый поиск.
          </span>
        )}
      </p>
      <Table
        columns={[
          "Вариант",
          "Рейсы и аэропорты",
          "Прибытие",
          "Длительность",
          "Пересадки",
          "Запас по MCT",
        ]}
        rows={result.options.map((r, i) => [
          i + 1,
          r.segments.map((f) => (
            <div key={f.id}>
              <Link to={"/flights/" + f.id}>{f.number}</Link> {f.origin} →{" "}
              {f.destination}
            </div>
          )),
          stamp(r.arrival, r.segments.at(-1)!.destination_zone),
          r.duration_minutes + " мин",
          r.stops,
          r.connections
            .map(
              (c) =>
                c.airport +
                " +" +
                (c.available_minutes - (c.minimum_minutes ?? 0)) +
                " мин",
            )
            .join(", ") || "—",
        ])}
      />
      {result.options.length > 0 && (
        <p className="pad muted">
          Порядок: раннее прибытие, меньше пересадок, затем меньшая
          длительность.
        </p>
      )}
    </Panel>
  );
}
function TripPage({ traveler }: { traveler: boolean }) {
  const { id } = useParams();
  const path = "/trips/" + id;
  const q = useData<Trip>(path);
  const act = useAction<Search | Assessment>();
  const [result, set] = useState<Search>();
  if (!q.data) return q.error ? <ErrorView error={q.error} /> : <Loading />;
  const t = q.data,
    a = t.assessments[0];
  return (
    <>
      <Link to="/trips">← Поездки</Link>
      <Head
        title={t.title}
        sub={
          t.flights.length +
          " сегмента · " +
          t.flights.map((f) => f.origin).join(" → ") +
          " → " +
          t.flights.at(-1)?.destination
        }
      >
        <Badge value={a.risk} />
      </Head>
      <Panel title="Пересадки">
        <Connections data={a.detail.connections} />
        <div className="toolbar pad">
          <button
            className="primary"
            disabled={act.isPending}
            onClick={() =>
              act.mutate(
                { path: path + "/alternatives" },
                {
                  onSuccess: (r) => {
                    if ("options" in r) set(r);
                  },
                },
              )
            }
          >
            Найти альтернативы
          </button>
          <button
            disabled={act.isPending}
            onClick={() => act.mutate({ path: path + "/recalculate" })}
          >
            Пересчитать
          </button>
        </div>
        <ErrorView error={act.error} />
      </Panel>
      {result && <SearchResults result={result} />}
      <Panel title="Сегменты поездки">
        <FlightTable data={t.flights} />
      </Panel>
      <Panel title="Нарушения поездки">
        <Table
          columns={["Причина", "Состояние", "Обнаружено UTC", "Действие"]}
          rows={t.incidents.map((i) => [
            name(i.reason),
            <Badge value={i.status} />,
            stamp(i.opened_at),
            traveler && i.status === "OPEN" ? (
              <button
                onClick={() =>
                  act.mutate({
                    path: path + "/incidents/" + i.id + "/acknowledge",
                  })
                }
              >
                Ознакомлен
              </button>
            ) : (
              "—"
            ),
          ])}
        />
      </Panel>
      <Panel title="История оценок">
        <Table
          columns={["Оценка", "Пересадка", "Причина", "Событие", "Время UTC"]}
          rows={t.assessments.map((a) => [
            a.id,
            <Badge value={a.risk} />,
            a.detail.reason ? name(a.detail.reason) : "—",
            a.event_sequence ?? "—",
            stamp(a.created_at),
          ])}
        />
      </Panel>
    </>
  );
}
function Planner() {
  const airports = useData<Airport[]>("/airports"),
    flights = useData<Flight[]>("/flights");
  const act = useAction<Search>();
  const first = flights.data?.[0]?.scheduled_dep.slice(0, 16);
  return (
    <>
      <Head
        title="Планирование маршрута"
        sub="Поиск по датированному расписанию с учётом минимального времени пересадки"
      />
      <Panel title="Параметры поиска">
        <form
          key={first}
          className="pad toolbar"
          onSubmit={(e) => {
            const f = form(e);
            act.mutate({
              path: "/routes",
              data: {
                origin: f.origin,
                destination: f.destination,
                earliest: String(f.earliest) + ":00Z",
                max_legs: Number(f.max_legs),
                max_hours: Number(f.max_hours),
              },
            });
          }}
        >
          {["origin", "destination"].map((k, i) => (
            <label key={k}>
              {i ? "Куда" : "Откуда"}
              <select name={k} defaultValue={i ? "FCO" : "OVB"}>
                {airports.data?.map((a) => (
                  <option key={a.code} value={a.code}>
                    {a.code} · {a.city}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <label>
            Не ранее, UTC
            <input
              type="datetime-local"
              name="earliest"
              defaultValue={first}
              required
            />
          </label>
          <label>
            Макс. сегментов
            <input
              type="number"
              name="max_legs"
              min={1}
              max={3}
              defaultValue={3}
              required
            />
          </label>
          <label>
            Горизонт, ч
            <input
              type="number"
              name="max_hours"
              min={1}
              max={72}
              defaultValue={36}
              required
            />
          </label>
          <button className="primary" disabled={act.isPending}>
            Найти маршруты
          </button>
        </form>
        <ErrorView error={act.error ?? airports.error} />
      </Panel>
      {act.data && <SearchResults result={act.data} />}
    </>
  );
}
function Disruptions() {
  const q = useData<Trip[]>("/trips");
  const trips = q.data?.filter((t) => t.disrupted) ?? [];
  return (
    <>
      <Head
        title="Центр нарушений"
        sub="Маршруты с риском, отменой или недоступным источником"
      />
      <Panel title="Поездки, требующие внимания">
        <ErrorView error={q.error} />
        {q.data ? (
          trips.length ? (
            <TripTable data={trips} />
          ) : (
            <p className="pad muted">Рискованных поездок сейчас нет.</p>
          )
        ) : (
          !q.error && <Loading />
        )}
      </Panel>
    </>
  );
}
function Notifications() {
  const q = useData<Notice[]>("/notifications"),
    act = useAction<Notice>();
  return (
    <>
      <Head title="Уведомления" sub="Изменения рейсов и состояния поездок" />
      <Panel title="Входящие">
        <ErrorView error={q.error ?? act.error} />
        {q.data ? (
          <Table
            columns={["Поездка", "Изменение", "Время UTC", "Статус"]}
            rows={q.data.map((n) => [
              <Link to={"/trips/" + n.trip}>{n.title}</Link>,
              name(n.kind),
              stamp(n.created_at),
              n.read_at ? (
                "Прочитано"
              ) : (
                <button
                  onClick={() =>
                    act.mutate({ path: "/notifications/" + n.id + "/read" })
                  }
                >
                  Отметить прочитанным
                </button>
              ),
            ])}
          />
        ) : (
          !q.error && <Loading />
        )}
      </Panel>
    </>
  );
}
function Provider() {
  const q = useData<Operations>("/operations"),
    act = useAction<unknown>();
  const f = q.data?.feed;
  return (
    <>
      <Head
        title="Мониторинг провайдера"
        sub="HTTP-опрос, контрольная точка и доступность источника"
      >
        <button
          className="primary"
          disabled={act.isPending}
          onClick={() => act.mutate({ path: "/operations/sync" })}
        >
          Синхронизировать
        </button>
      </Head>
      <ErrorView error={q.error ?? act.error} />
      {f ? (
        <>
          <div className="metrics">
            {[
              ["Последовательность", f.cursor],
              ["Версия расписания", f.generation],
              [
                "Доступность",
                f.fresh ? "Данные актуальны" : "Данные недоступны",
              ],
              ["Последний опрос UTC", stamp(f.last_success)],
            ].map(([label, value]) => (
              <section key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </section>
            ))}
          </div>
          <Panel title="Запуски синхронизации">
            <Table
              columns={[
                "Запуск",
                "Результат",
                "С курсора",
                "До курсора",
                "Время UTC",
              ]}
              rows={q.data!.runs.map((r) => [
                r.id,
                r.status,
                r.start_cursor,
                r.end_cursor,
                stamp(r.created_at),
              ])}
            />
          </Panel>
        </>
      ) : (
        !q.error && <Loading />
      )}
    </>
  );
}
function Explorer() {
  const q = useData<Operations>("/operations");
  return (
    <>
      <Head
        title="Журнал событий"
        sub="Версия источника, результат обработки и время получения"
      />
      <Panel title="Поток обновлений">
        <ErrorView error={q.error} />
        {q.data ? (
          <EventTable events={q.data.events} />
        ) : (
          !q.error && <Loading />
        )}
      </Panel>
    </>
  );
}
function Policies() {
  const q = useData<Policy[]>("/policies"),
    act = useAction<Policy>();
  return (
    <>
      <Head
        title="Учебные правила пересадки"
        sub="Минимальное время и запас на смену терминала"
      />
      <Panel title="Новая версия">
        <form
          className="pad toolbar"
          onSubmit={(e) => {
            const v = form(e);
            act.mutate({
              path: "/policies/" + v.airport,
              data: {
                domestic: Number(v.domestic),
                international: Number(v.international),
                terminal_extra: Number(v.terminal_extra),
              },
            });
          }}
        >
          <label>
            Аэропорт
            <select name="airport">
              {[...new Set(q.data?.map((x) => x.airport))].map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </label>
          <label>
            Внутренняя, мин
            <input name="domestic" type="number" min={15} max={240} required />
          </label>
          <label>
            Международная, мин
            <input
              name="international"
              type="number"
              min={15}
              max={240}
              required
            />
          </label>
          <label>
            Смена терминала, мин
            <input
              name="terminal_extra"
              type="number"
              min={0}
              max={90}
              required
            />
          </label>
          <button className="primary" disabled={act.isPending}>
            Опубликовать
          </button>
        </form>
        <ErrorView error={act.error ?? q.error} />
      </Panel>
      <Panel title="История политик">
        <Table
          columns={[
            "Аэропорт",
            "Версия",
            "Внутренняя",
            "Международная",
            "Терминал",
          ]}
          rows={(q.data ?? []).map((p) => [
            p.airport,
            p.version,
            p.domestic,
            p.international,
            p.terminal_extra,
          ])}
        />
      </Panel>
    </>
  );
}
function Users() {
  const users = useData<User[]>("/users"),
    act = useAction<User>();
  return (
    <>
      <Head title="Пользователи" />
      <Panel title="Учётные записи">
        <ErrorView error={users.error} />
        <Table
          columns={["Логин", "Имя", "Роль"]}
          rows={(users.data ?? []).map((u) => [u.login, u.name, name(u.role)])}
        />
      </Panel>
      <Panel title="Создать пользователя">
        <form
          className="pad form"
          onSubmit={(e) => act.mutate({ path: "/users", data: form(e) })}
        >
          <label>
            Логин
            <input name="login" required />
          </label>
          <label>
            Имя
            <input name="name" required minLength={2} />
          </label>
          <label>
            Пароль
            <input name="password" type="password" required minLength={12} />
          </label>
          <label>
            Роль
            <select name="role">
              {["TRAVELER", "OPERATIONS_ANALYST", "ADMIN"].map((r) => (
                <option key={r} value={r}>
                  {name(r)}
                </option>
              ))}
            </select>
          </label>
          <button className="primary" disabled={act.isPending}>
            Создать
          </button>
          <ErrorView error={act.error} />
          {act.data && (
            <p role="status">Пользователь {act.data.login} создан.</p>
          )}
        </form>
      </Panel>
    </>
  );
}
function Lab({ scenarios }: { scenarios: Record<string, string> }) {
  const act = useAction<{
    passed: boolean;
    checks: Record<string, boolean>;
    before: unknown;
    after: unknown;
    trace: unknown;
  }>();
  return (
    <>
      <Head
        title="Wayline Lab"
        sub="Независимый провайдер, HTTP-события и изолированная база"
      />
      <Panel title="Эксперимент">
        <form
          className="pad toolbar"
          onSubmit={(e) => act.mutate({ path: "/lab/" + form(e).scenario })}
        >
          <label>
            Сценарий
            <select name="scenario">
              {Object.entries(scenarios).map(([id, n]) => (
                <option key={id} value={id}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button className="primary" disabled={act.isPending}>
            {act.isPending ? "Выполняется…" : "Запустить сценарий"}
          </button>
        </form>
        <ErrorView error={act.error} />
      </Panel>
      {act.data && (
        <Panel
          title={act.data.passed ? "Проверка пройдена" : "Проверка не пройдена"}
        >
          <Table
            columns={["Инвариант", "Результат"]}
            rows={Object.entries(act.data.checks).map(([k, v]) => [
              k,
              v ? "✓" : "Ошибка",
            ])}
          />
          <details>
            <summary>Запросы и ответы</summary>
            <Json data={act.data.trace} />
          </details>
          <details>
            <summary>Состояние до и после</summary>
            <Json data={{ before: act.data.before, after: act.data.after }} />
          </details>
        </Panel>
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <HashRouter>
      <App />
    </HashRouter>
  </QueryClientProvider>,
);
