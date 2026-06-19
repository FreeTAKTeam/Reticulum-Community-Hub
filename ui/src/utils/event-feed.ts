import type { ClientEntry, EventEntry, IdentityEntry, RemPeerEntry, TeamMemberRecord } from "../api/types";

const IDENTITY_METADATA_KEYS = new Set([
  "announced_identity_hash",
  "assigned_by",
  "changed_by",
  "changed_by_team_member_rns_identity",
  "client_identity",
  "completed_by_team_member_rns_identity",
  "created_by",
  "created_by_team_member_rns_identity",
  "destination",
  "destination_hash",
  "identity",
  "node",
  "object_destination_hash",
  "peer",
  "peer_destination",
  "recipient",
  "recipient_hash",
  "source",
  "source_identity",
  "target",
  "team_member_rns_identity",
  "updated_by_team_member_rns_identity"
]);

const normalizeLookupKey = (value: unknown): string => String(value ?? "").trim().toLowerCase();

const toText = (value: unknown): string => String(value ?? "").trim();

const toStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(toText).filter((entry) => entry.length > 0);
};

type EventCallsignSources = {
  teamMembers?: TeamMemberRecord[];
  clients?: ClientEntry[];
  identities?: IdentityEntry[];
  remPeers?: RemPeerEntry[];
};

const setLookupValue = (lookup: Map<string, string>, token: unknown, callsign: string) => {
  const key = normalizeLookupKey(token);
  if (key && !lookup.has(key)) {
    lookup.set(key, callsign);
  }
};

const asArray = <T>(value: T[] | undefined): T[] => (Array.isArray(value) ? value : []);

const formatAnnounceName = (value: string): string => {
  const name = value.trim();
  if (!name) {
    return "";
  }
  if (name === name.toLowerCase()) {
    return `${name.charAt(0).toUpperCase()}${name.slice(1)}`;
  }
  return name;
};

const nameFromText = (value: unknown): string => {
  const text = toText(value);
  const match = text.match(/(?:^|[;,]\s*)name=([^;,]+)/i);
  return match ? formatAnnounceName(match[1]) : "";
};

const nameFromCapabilities = (capabilities: unknown): string => {
  return toStringList(capabilities)
    .map(nameFromText)
    .find((name) => name.length > 0) ?? "";
};

const labelFromAnnounce = (displayName: unknown, capabilities: unknown): string => {
  const displayText = toText(displayName);
  return nameFromText(displayText) || nameFromCapabilities(capabilities) || displayText;
};

const normalizeSources = (sources: TeamMemberRecord[] | EventCallsignSources): Required<EventCallsignSources> => {
  if (Array.isArray(sources)) {
    return {
      teamMembers: sources,
      clients: [],
      identities: [],
      remPeers: []
    };
  }
  return {
    teamMembers: asArray(sources.teamMembers),
    clients: asArray(sources.clients),
    identities: asArray(sources.identities),
    remPeers: asArray(sources.remPeers)
  };
};

export const buildEventCallsignLookup = (sources: TeamMemberRecord[] | EventCallsignSources): Map<string, string> => {
  const lookup = new Map<string, string>();
  const { teamMembers, clients, identities, remPeers } = normalizeSources(sources);

  teamMembers.forEach((member) => {
    const label = toText(member.callsign) || toText(member.display_name);
    if (!label) {
      return;
    }
    setLookupValue(lookup, member.rns_identity, label);
    setLookupValue(lookup, member.uid, label);
    toStringList(member.client_identities).forEach((identity) => setLookupValue(lookup, identity, label));
  });

  clients.forEach((client) => {
    const label = labelFromAnnounce(client.display_name, client.announce_capabilities);
    if (!label) {
      return;
    }
    setLookupValue(lookup, client.id, label);
    setLookupValue(lookup, client.identity_id, label);
  });

  identities.forEach((identity) => {
    const label = labelFromAnnounce(identity.display_name, identity.announce_capabilities);
    if (!label) {
      return;
    }
    setLookupValue(lookup, identity.id, label);
    setLookupValue(lookup, identity.announce_destination_hash, label);
    setLookupValue(lookup, identity.announced_identity_hash, label);
  });

  remPeers.forEach((peer) => {
    const label = labelFromAnnounce(peer.display_name, peer.announce_capabilities);
    if (!label) {
      return;
    }
    setLookupValue(lookup, peer.identity, label);
    setLookupValue(lookup, peer.destination_hash, label);
  });
  return lookup;
};

const shouldReadMetadataKey = (key: string): boolean => {
  const normalized = key.trim().toLowerCase();
  return IDENTITY_METADATA_KEYS.has(normalized);
};

const collectIdentityTokens = (value: unknown, tokens: Set<string>, parentKey = "") => {
  if (typeof value === "string") {
    if (parentKey && shouldReadMetadataKey(parentKey)) {
      const token = value.trim();
      if (token) {
        tokens.add(token);
      }
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((entry) => collectIdentityTokens(entry, tokens, parentKey));
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }
  Object.entries(value as Record<string, unknown>).forEach(([key, entry]) => {
    collectIdentityTokens(entry, tokens, key);
  });
};

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const replaceToken = (message: string, token: string, callsign: string): string => {
  const escaped = escapeRegExp(token);
  return message.replace(new RegExp(`(^|[^A-Za-z0-9])(${escaped})(?=$|[^A-Za-z0-9])`, "gi"), `$1${callsign}`);
};

const isMarkerCreatedEvent = (event: EventEntry): boolean => {
  return (
    normalizeLookupKey(event.category) === "marker_created" ||
    normalizeLookupKey(event.metadata?.event_type) === "marker.created"
  );
};

const formatMarkerCreatedMessage = (event: EventEntry, message: string): string => {
  if (!isMarkerCreatedEvent(event)) {
    return message;
  }
  return message.replace(/^Marker created:\s+(.+?)[+-][0-9a-f]{6}$/i, "Marker created: $1");
};

export const resolveEventFeedMessage = (
  event: EventEntry,
  callsignByIdentity: ReadonlyMap<string, string>
): string => {
  const message = toText(event.message) || "Event received";
  const metadataTokens = new Set<string>();
  collectIdentityTokens(event.metadata, metadataTokens);

  const replacements = [...metadataTokens]
    .map((token) => ({
      token,
      callsign: callsignByIdentity.get(normalizeLookupKey(token))
    }))
    .filter((entry): entry is { token: string; callsign: string } => Boolean(entry.callsign));

  const fallbackReplacements =
    replacements.length > 0
      ? []
      : [...callsignByIdentity.entries()]
          .filter(([token]) => token.length >= 6 && message.toLowerCase().includes(token))
          .map(([token, callsign]) => ({ token, callsign }));

  const resolvedMessage = [...replacements, ...fallbackReplacements]
    .sort((left, right) => right.token.length - left.token.length)
    .reduce((current, entry) => replaceToken(current, entry.token, entry.callsign), message);
  return formatMarkerCreatedMessage(event, resolvedMessage);
};
