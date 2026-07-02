import { get, post } from "./client";
import { endpoints } from "./endpoints";

export interface SetupStatus {
  setup_required: boolean;
  pin_enrolled: boolean;
  pin_created_at?: string | null;
  hub_name?: string | null;
  remote_password_configured: boolean;
  remote_password_created_at?: string | null;
  config_path?: string | null;
  reticulum_config_path?: string | null;
  reticulum_identity_hash?: string | null;
  reticulum_identity_path?: string | null;
  reticulum_identity_created?: boolean | null;
}

export interface CompleteSetupPayload {
  hub_name: string;
  remote_password: string;
  kill_switch_pin: string;
  reticulum_config_text?: string;
}

export const fetchSetupStatus = () =>
  get<SetupStatus>(endpoints.setupStatus, {
    retries: 0,
    skipAuthValidation: true
  });

export const completeSetup = (payload: CompleteSetupPayload) =>
  post<SetupStatus>(endpoints.setupComplete, payload, {
    skipAuthValidation: true
  });
