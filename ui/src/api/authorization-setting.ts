import { get, put } from "./client";
import { endpoints } from "./endpoints";

/** Wire shape of `GET/PUT /api/r3akt/settings/authorization`. */
export interface AuthorizationSetting {
  authorization_required: boolean;
}

/** Narrows an untrusted response; an incompatible payload is an error, not "off". */
export const decodeAuthorizationSetting = (value: unknown): AuthorizationSetting => {
  if (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>).authorization_required === "boolean"
  ) {
    return { authorization_required: (value as { authorization_required: boolean }).authorization_required };
  }
  throw new Error("Unexpected authorization setting response from the hub");
};

export const fetchAuthorizationSetting = async (): Promise<AuthorizationSetting> =>
  decodeAuthorizationSetting(await get<unknown>(endpoints.r3aktAuthorizationSetting));

export const saveAuthorizationSetting = async (required: boolean): Promise<AuthorizationSetting> =>
  decodeAuthorizationSetting(
    await put<unknown>(endpoints.r3aktAuthorizationSetting, { authorization_required: required })
  );
