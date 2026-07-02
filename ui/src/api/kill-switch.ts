import { get, post } from "./client";
import { endpoints } from "./endpoints";

export type KillSwitchState = "idle" | "armed" | "authorized" | "deleting" | "completed" | "failed";
export type KillSwitchTargetState = "queued" | "erasing" | "erased" | "failed";

export interface KillSwitchTarget {
  id: string;
  label: string;
  short: string;
  total: number;
  erased: number;
  unit: "records" | "objects" | "tokens" | "bytes";
  state: KillSwitchTargetState;
  weight: number;
}

export interface KillSwitchStatus {
  state: KillSwitchState;
  arm_a: boolean;
  arm_b: boolean;
  pin_enrolled: boolean;
  pin_created_at?: string | null;
  initial_pin?: string | null;
  authorized_at?: string | null;
  purge_started_at?: string | null;
  progress_percent: number;
  message: string;
  targets: KillSwitchTarget[];
  updated_at: string;
}

export const fetchKillSwitchStatus = () => get<KillSwitchStatus>(endpoints.killSwitchStatus);

export const setKillSwitchArms = (armA: boolean, armB: boolean) =>
  post<KillSwitchStatus>(endpoints.killSwitchArm, { arm_a: armA, arm_b: armB });

export const authorizeKillSwitch = (pin: string) =>
  post<KillSwitchStatus>(endpoints.killSwitchAuthorize, { pin }, { suppressAuthStatus: true });

export const startKillSwitchPurge = () =>
  post<KillSwitchStatus>(endpoints.killSwitchPurge);
