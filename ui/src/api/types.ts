export interface StatusResponse {
  app_info?: {
    name?: string;
    version?: string;
  };
  clients?: number;
  topics?: number;
  subscribers?: number;
  files?: number;
  images?: number;
  telemetry?: {
    total?: number;
    ingest_count?: number;
    last_ingest_at?: string;
  };
  chat?: {
    sent?: number;
    failed?: number;
    received?: number;
  };
  uptime?: number;
  uptime_seconds?: number;
}

export interface EventEntry {
  id?: string;
  created_at?: string;
  message?: string;
  level?: string;
  category?: string;
  metadata?: Record<string, unknown>;
}

export interface Topic {
  id?: string;
  name?: string;
  path?: string;
  description?: string;
}

export interface Subscriber {
  id?: string;
  topic_id?: string;
  destination?: string;
  reject_tests?: boolean;
  metadata?: Record<string, unknown>;
}

export interface FileEntry {
  id?: string;
  name?: string;
  content_type?: string;
  size?: number;
  created_at?: string;
}

export interface IdentityEntry {
  id?: string;
  display_name?: string;
  status?: string;
  last_seen?: string;
  banned?: boolean;
  blackholed?: boolean;
}

export interface ClientEntry {
  id?: string;
  last_seen_at?: string;
  identity_id?: string;
  display_name?: string;
  metadata?: Record<string, unknown>;
}

export interface TelemetryEntry {
  id?: string;
  identity_id?: string;
  identity?: string;
  identity_label?: string;
  display_name?: string;
  topic_id?: string;
  created_at?: string;
  location?: {
    lat?: number;
    lon?: number;
    alt?: number;
  };
  data?: Record<string, unknown>;
}

export interface MarkerEntry {
  object_destination_hash?: string;
  origin_rch?: string;
  object_identity_storage_key?: string;
  marker_id?: string;
  type?: string;
  name?: string;
  category?: string;
  symbol?: string;
  notes?: string | null;
  position?: {
    lat?: number;
    lon?: number;
  };
  time?: string;
  stale_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ZonePoint {
  lat?: number;
  lon?: number;
}

export interface ZoneEntry {
  zone_id?: string;
  name?: string;
  points?: ZonePoint[];
  created_at?: string;
  updated_at?: string;
}

export interface MarkerSymbolEntry {
  id?: string;
  set?: string;
  mdi?: string;
  description?: string;
  tak?: string;
  category?: string;
}

export interface AppInfo {
  name?: string;
  version?: string;
  description?: string;
  rns_version?: string;
  lxmf_version?: string;
  reticulum_destination?: string;
  storage_paths?: Record<string, string>;
}

export interface ChatAttachment {
  file_id?: number;
  category?: string;
  name?: string;
  size?: number;
  media_type?: string | null;
}

export interface ChatMessage {
  message_id?: string;
  direction?: string;
  scope?: string;
  state?: string;
  content?: string;
  source?: string | null;
  destination?: string | null;
  topic_id?: string | null;
  attachments?: ChatAttachment[];
  created_at?: string;
  updated_at?: string;
}
