export type StageStatus = "pending" | "running" | "succeeded" | "failed";

export type JobStatus = "pending" | "running" | "succeeded" | "failed";

export interface Stage {
  name: string;
  status: StageStatus;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
}

export interface Field {
  name: string;
  type: string;
  required?: boolean;
  unique?: boolean;
}

export interface Entity {
  name: string;
  fields: Field[];
}

export interface Endpoint {
  method: string;
  path: string;
  auth?: boolean;
  summary?: string;
}

export interface Screen {
  name: string;
  route: string;
  auth?: boolean;
  components?: string[];
  actions?: string[];
}

export interface Spec {
  app: { name: string; summary: string; version: string };
  stack: { frontend: string; backend: string; db: string };
  entities: Entity[];
  auth?: { type: "none" | "jwt"; roles?: string[] } | null;
  endpoints: Endpoint[];
  screens: Screen[];
  integrations?: string[];
  non_functional?: { i18n?: boolean; analytics?: boolean; tests?: string };
}

export interface Job {
  id: string;
  status: JobStatus;
  stages: Stage[];
  spec: Spec | null;
  error: string | null;
  artifact_ready: boolean;
  created_at: string;
  updated_at: string;
}
