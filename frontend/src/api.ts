let token = "";
export const setToken = (value: string) => {
  token = value;
};
export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers: {
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(data === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  if (response.status === 204) return undefined as T;
  const result = await response.json();
  if (!response.ok) throw Error(result.detail + " · HTTP " + response.status);
  return result;
}
export type User = { login: string; name: string; role: string };
export type Flight = {
  id: string;
  number: string;
  origin: string;
  destination: string;
  origin_zone: string;
  destination_zone: string;
  origin_city: string;
  destination_city: string;
  scheduled_dep: string;
  scheduled_arr: string;
  estimated_dep: string | null;
  estimated_arr: string | null;
  actual_dep: string | null;
  actual_arr: string | null;
  status: string;
  revision: number;
  terminal_dep: string;
  terminal_arr: string;
  events?: Event[];
};
export type Event = {
  sequence: number;
  event_id: string;
  flight: string;
  disposition: string;
  revision: number;
  source_time: string;
  received_at: string;
  payload: unknown;
};
export type Connection = {
  airport: string;
  planned_minutes: number;
  available_minutes: number;
  minimum_minutes: number | null;
  policy_version: number | null;
  risk: string;
  terminal_change: boolean;
  inbound: string;
  outbound: string;
};
export type Assessment = {
  id: number;
  risk: string;
  created_at: string;
  event_sequence: number | null;
  detail: { reason: string | null; fresh: boolean; connections: Connection[] };
};
export type Trip = {
  id: string;
  title: string;
  owner: string;
  risk: string;
  disrupted: boolean;
  flights: Flight[];
  assessments: Assessment[];
  incidents: {
    id: string;
    status: string;
    reason: string;
    opened_at: string;
    resolved_at: string | null;
  }[];
  feed: Feed;
};
export type Route = {
  segments: Flight[];
  connections: Connection[];
  arrival: string;
  duration_minutes: number;
  stops: number;
  explanation: string;
};
export type Search = {
  id: string;
  generation: number;
  status: string;
  current?: boolean;
  options: Route[];
};
export type Feed = {
  cursor: number;
  fresh: boolean;
  last_success: string | null;
  last_error: string | null;
  generation: number;
};
export type Operations = {
  feed: Feed;
  counts: Record<string, number>;
  runs: {
    id: number;
    status: string;
    start_cursor: number;
    end_cursor: number;
    created_at: string;
  }[];
  events: Event[];
};
export type Airport = {
  code: string;
  city: string;
  zone: string;
  country: string;
};
export type Notice = {
  id: number;
  trip: string;
  title: string;
  kind: string;
  read_at: string | null;
  created_at: string;
};
export type Policy = {
  airport: string;
  version: number;
  domestic: number;
  international: number;
  terminal_extra: number;
};
