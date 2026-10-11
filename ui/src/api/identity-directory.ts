import { get } from "./client";
import { endpoints } from "./endpoints";
import type { IdentityEntry } from "./types";

export type IdentityQuery = { page: number; view: "recent" | "all"; search: string; clientType: "all" | "rem" | "generic_lxmf"; order: "last_seen_desc" | "identity_asc" };
export type IdentityDirectorySettings = { pageSize: number; recentHours: number; lookupMaxEntries: number; lookupConcurrency: number };
export class UnsupportedIdentityDirectory extends Error {}
const record = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const positive = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value > 0;
export const normalizeIdentity = (value: string) => value.trim().replace(/[A-Z]/g, (letter) => letter.toLowerCase());
export const loadIdentitySettings = async (signal: AbortSignal): Promise<IdentityDirectorySettings> => {
  const info = await get<unknown>(endpoints.appInfo, { signal });
  const value = record(info) ? info.identity_directory : undefined;
  if (!record(value) || value.supported !== true) { throw new UnsupportedIdentityDirectory("This backend does not support searchable, paginated identities. Users, Chat and Topics remain available."); }
  if (![value.page_size, value.recent_hours, value.lookup_max_entries, value.lookup_concurrency].every(positive) ||
    Number(value.page_size) > 500 || Number(value.lookup_max_entries) > 10000 || Number(value.lookup_concurrency) > 16) {
    throw new Error("Invalid identity-directory configuration returned by the backend.");
  }
  return { pageSize: value.page_size as number, recentHours: value.recent_hours as number,
    lookupMaxEntries: value.lookup_max_entries as number, lookupConcurrency: value.lookup_concurrency as number };
};
export const decodeIdentity = (value: unknown): IdentityEntry => {
  if (!record(value) || typeof value.Identity !== "string" || !value.Identity.trim()) { throw new Error("Invalid identity entry."); }
  for (const key of ["DisplayName", "Status", "LastSeen", "RemMode", "AnnounceDestinationHash", "AnnouncedIdentityHash", "AnnounceSource", "AnnounceFirstSeen", "AnnounceLastSeen", "RecentlyHeardAt", "ClientType"]) {
    if (value[key] !== undefined && value[key] !== null && typeof value[key] !== "string") { throw new Error(`Invalid identity ${key}.`); }
  }
  for (const key of ["IsBanned", "IsBlackholed", "IsRemCapable", "IsAnnounced"]) {
    if (value[key] !== undefined && typeof value[key] !== "boolean") { throw new Error(`Invalid identity ${key}.`); }
  }
  if (value.Metadata !== undefined && value.Metadata !== null && !record(value.Metadata)) { throw new Error("Invalid identity metadata."); }
  if (value.AnnounceCapabilities !== undefined && (!Array.isArray(value.AnnounceCapabilities) || !value.AnnounceCapabilities.every((item) => typeof item === "string"))) { throw new Error("Invalid identity capabilities."); }
  const text = (key: string) => typeof value[key] === "string" ? value[key] as string : undefined;
  const metadata = record(value.Metadata) ? value.Metadata : undefined;
  const metadataName = metadata?.display_name ?? metadata?.displayName ?? metadata?.DisplayName ?? metadata?.name ?? metadata?.label;
  return { id: text("Identity"), display_name: text("DisplayName") ?? (typeof metadataName === "string" ? metadataName : undefined), status: text("Status"),
    last_seen: text("AnnounceLastSeen") ?? text("LastSeen"), recently_heard_at: text("RecentlyHeardAt"), metadata,
    banned: value.IsBanned as boolean | undefined, blackholed: value.IsBlackholed as boolean | undefined,
    client_type: text("ClientType"), announce_capabilities: value.AnnounceCapabilities as string[] | undefined,
    rem_mode: text("RemMode"), is_rem_capable: value.IsRemCapable as boolean | undefined, is_announced: value.IsAnnounced as boolean | undefined,
    announce_destination_hash: text("AnnounceDestinationHash"), announced_identity_hash: text("AnnouncedIdentityHash"),
    announce_source: text("AnnounceSource"), announce_first_seen: text("AnnounceFirstSeen"), announce_last_seen: text("AnnounceLastSeen") };
};
export const loadIdentityPage = async (query: IdentityQuery, perPage: number, signal: AbortSignal, identity?: string) => {
  const params = new URLSearchParams({ page: String(query.page), per_page: String(perPage), view: query.view, search: query.search,
    client_type: query.clientType, order: query.order });
  if (identity) { params.set("identity", normalizeIdentity(identity)); }
  const value = await get<unknown>(`${endpoints.identities}?${params}`, { signal });
  if (Array.isArray(value)) { throw new UnsupportedIdentityDirectory("This backend returned a legacy full directory. Searchable identity paging is unavailable."); }
  if (!record(value) || !Array.isArray(value.items) || typeof value.total !== "number" || !Number.isSafeInteger(value.total) || value.total < 0 ||
    value.page !== query.page || value.per_page !== perPage || value.items.length > perPage ||
    value.total_pages !== Math.ceil(value.total / perPage) || value.has_next !== (query.page < Math.ceil(value.total / perPage)) ||
    value.items.length !== Math.min(perPage, Math.max(0, value.total - (query.page - 1) * perPage))) {
    throw new Error("Invalid identity pagination response.");
  }
  return { items: value.items.map(decodeIdentity), total: value.total };
};
