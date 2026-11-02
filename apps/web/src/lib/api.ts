export type Role =
  | 'viewer'
  | 'mission_planner'
  | 'operator'
  | 'simulator_engineer';

export interface Drone {
  drone_id: string;
  name: string;
  state: string;
  health: string;
  battery_percent: number;
  gps_quality: string;
  link_quality_percent: number;
  profile: { name: string };
  last_observed_at: string;
}

export interface Mission {
  mission_id: string;
  state: string;
  assigned_drone_id: string | null;
  minimum_landing_reserve_percent: number;
}

export interface EventRecord {
  event_id: string;
  event_type: string;
  occurred_at: string;
  producer: string;
  payload: Record<string, unknown>;
}

export interface Eligibility {
  mission_id: string;
  selected_drone_id: string | null;
  drones: Array<{
    drone_id: string;
    eligible: boolean;
    score: number | null;
    reasons: Array<{ rule_id: string; reason: string; decision: string }>;
  }>;
}

export function statusLabel(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function apiHeaders(
  role: Role,
  idempotencyKey?: string
): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Treta-Actor': `local-${role}`,
    'X-Treta-Role': role,
    'X-Treta-Tenant-ID': 'tenant-synthetic'
  };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  return headers;
}

export function createApi(baseUrl: string) {
  let sequence = 0;

  async function request<T>(
    path: string,
    role: Role,
    method = 'GET',
    body?: unknown
  ): Promise<T> {
    sequence += 1;
    const response = await fetch(`${baseUrl}${path}`, {
      method,
      headers: apiHeaders(
        role,
        method === 'GET' ? undefined : `ui-${sequence}`
      ),
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    const data: unknown = await response.json();
    if (!response.ok) {
      const detail =
        (data as { error?: { detail?: string } }).error?.detail ??
        response.statusText;
      throw new Error(detail);
    }
    return data as T;
  }

  return { request };
}
