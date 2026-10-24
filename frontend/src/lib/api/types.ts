// Hand-written to match the backend contract until `npm run api:types`
// generates src/lib/api/schema.d.ts.
export interface User {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export type ServiceStatus = "ok" | "error" | (string & {});

export interface HealthResponse {
  status: "ok" | "degraded" | (string & {});
  services: Record<string, ServiceStatus>;
  version: string;
}
