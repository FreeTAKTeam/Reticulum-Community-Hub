-- Payload-derived indexes for bounded runtime diagnostics and identity lookups.
-- Rust streams the legacy MessagePack payloads into these columns in the same
-- migration transaction; the original payload bytes remain unchanged.
ALTER TABLE rch_identity_announces ADD COLUMN last_seen_ts_ms INTEGER;
ALTER TABLE rch_identity_announces ADD COLUMN normalized_destination_hash TEXT;
ALTER TABLE rch_identity_announces ADD COLUMN normalized_announced_identity_hash TEXT;
CREATE INDEX idx_rch_announces_recent
    ON rch_identity_announces (last_seen_ts_ms DESC, destination_hash ASC);
CREATE INDEX idx_rch_announces_destination
    ON rch_identity_announces (normalized_destination_hash, last_seen_ts_ms);
CREATE INDEX idx_rch_announces_identity
    ON rch_identity_announces (normalized_announced_identity_hash, last_seen_ts_ms);
-- Preview.12 and earlier INSERT/REPLACE writers omit the projections. Reject
-- those writes instead of allowing a newer reader to trust incomplete indexes.
CREATE TRIGGER rch_announces_require_projection_insert
BEFORE INSERT ON rch_identity_announces WHEN NEW.last_seen_ts_ms IS NULL
BEGIN
    SELECT RAISE(ABORT, 'announce projections required; stop older RCH writers');
END;
CREATE TRIGGER rch_announces_require_projection_update
BEFORE UPDATE ON rch_identity_announces WHEN NEW.last_seen_ts_ms IS NULL
BEGIN
    SELECT RAISE(ABORT, 'announce projections required; stop older RCH writers');
END;
