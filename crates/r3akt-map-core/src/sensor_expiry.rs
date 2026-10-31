//! Optional source expiry for imported `CoT` samples; source timestamps remain unchanged.
use serde::{Deserialize, Serialize};
pub const EVENT: &str = "mission.registry.sensor.expiry";
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SensorExpiry {
    pub origin_id: String,
    pub sensor_id: String,
    pub sample_at_ms: u64,
    pub expires_at_ms: u64,
}
impl SensorExpiry {
    /// # Errors
    /// Rejects invalid identities, timestamps and expiries outside a one-day source interval.
    pub fn validate(&self) -> Result<(), &'static str> {
        crate::marker::object_destination_hash(&self.origin_id)
            .map_err(|_| "invalid expiry origin")?;
        crate::sensor::sensor_id(&self.sensor_id)?;
        crate::sensor::valid_time(self.sample_at_ms)?;
        crate::sensor::valid_time(self.expires_at_ms)?;
        if self.expires_at_ms < self.sample_at_ms
            || self.expires_at_ms - self.sample_at_ms > 86_400_000
        {
            return Err("invalid sensor source expiry");
        }
        Ok(())
    }
}
#[cfg(feature = "sqlite")]
impl super::sensor_store::SensorOrigin {
    /// # Errors
    /// Rejects an expiry that contradicts an already accepted sample revision.
    pub fn apply_expiry(
        &mut self,
        expiry: &SensorExpiry,
    ) -> Result<bool, super::sensor_store::StoreError> {
        expiry
            .validate()
            .map_err(super::sensor_store::StoreError::Invalid)?;
        if self
            .sensors
            .get(&expiry.sensor_id)
            .is_none_or(|s| s.sample_at_ms != expiry.sample_at_ms)
        {
            return Ok(false);
        }
        if let Some(time) = self.sensor_expiry_ms.get(&expiry.sensor_id) {
            if *time != expiry.expires_at_ms {
                return Err(super::sensor_store::StoreError::Invalid(
                    "conflicting sensor source expiry",
                ));
            }
            return Ok(false);
        }
        self.sensor_expiry_ms
            .insert(expiry.sensor_id.clone(), expiry.expires_at_ms);
        Ok(true)
    }
}

#[cfg(feature = "sqlite")]
/// # Errors
/// Rejects unbound writers, malformed expiry or contradictory accepted revisions.
pub fn store(
    connection: &rusqlite::Connection,
    writer: &str,
    expiry: &SensorExpiry,
) -> Result<bool, super::sensor_store::StoreError> {
    super::sensor_store::mutate(connection, &expiry.origin_id, writer, |origin| {
        origin.apply_expiry(expiry)
    })
}
