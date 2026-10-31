use super::{MessageRecord, OptionalExtension, RchCommandTransaction, RchCoreError, params};
impl RchCommandTransaction<'_> {
    pub fn sensor_relay_metadata(
        &self,
        id: &str,
        destination: &str,
    ) -> Result<Option<String>, RchCoreError> {
        Ok(self
            .transaction
            .query_row(
                "SELECT hash FROM r3s_relay_metadata WHERE origin_id=?1 AND destination=?2",
                params![id, destination],
                |r| r.get(0),
            )
            .optional()?)
    }
    pub(super) fn confirm_delivered_sensor_metadata(
        &self,
        message: &MessageRecord,
    ) -> Result<(), RchCoreError> {
        if message.delivery_state != "delivered" {
            return Ok(());
        }
        let policy = &message.delivery_metadata["r3s_policy"];
        if policy["includeMetadata"] == true
            && let (Some(id), Some(hash), Some(destination)) = (
                policy["originId"].as_str(),
                policy["metadataHash"].as_str(),
                message.destination.as_deref(),
            )
        {
            self.transaction.execute("INSERT INTO r3s_relay_metadata VALUES (?1,?2,?3) ON CONFLICT(origin_id,destination) DO UPDATE SET hash=excluded.hash",params![id,destination,hash])?;
        }
        Ok(())
    }
}
