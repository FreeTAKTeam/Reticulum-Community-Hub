//! Durable history and bounded runtime hydration; presentation is never the history owner.
use super::{
    ChatAttachmentRecord, Connection, MessageRecord, RchCoreError, RchSqliteStore, SqlValue, Value,
    decode_msgpack, encode_msgpack, message_queue_projection, params, params_from_iter,
    sql_optional_text, sql_text, sqlite_read_usize, sqlite_u64,
};
use std::fmt::Write;

pub const RECENT_MESSAGE_COUNT: usize = 500;
pub const RECENT_MESSAGE_BYTES: usize = 32 * 1024 * 1024;
pub const RECENT_MESSAGE_IDLE_MS: i64 = 30 * 60 * 1000;

/// Conservative retained-heap estimate, including JSON containers and their strings.
#[must_use]
pub fn json_resident_bytes(value: &Value) -> usize {
    match value {
        Value::String(text) => text.capacity().saturating_add(32),
        Value::Array(values) => values.iter().fold(
            values
                .capacity()
                .saturating_mul(std::mem::size_of::<Value>()),
            |bytes, value| bytes.saturating_add(json_resident_bytes(value)),
        ),
        Value::Object(values) => values.iter().fold(0_usize, |bytes, (key, value)| {
            bytes
                .saturating_add(key.capacity())
                .saturating_add(128)
                .saturating_add(json_resident_bytes(value))
        }),
        _ => 32,
    }
}
impl MessageRecord {
    pub fn estimated_resident_bytes(&self) -> usize {
        let strings = [
            &self.message_id,
            &self.sender,
            &self.content,
            &self.delivery_method,
            &self.delivery_policy_reason,
            &self.delivery_state,
        ];
        let mut bytes = strings.iter().fold(4096_usize, |bytes, text| {
            bytes.saturating_add(text.capacity())
        });
        for text in [&self.topic_id, &self.destination].into_iter().flatten() {
            bytes = bytes.saturating_add(text.capacity());
        }
        bytes = bytes.saturating_add(json_resident_bytes(&self.delivery_metadata));
        bytes = bytes.saturating_add(
            self.attachments
                .capacity()
                .saturating_mul(std::mem::size_of::<ChatAttachmentRecord>()),
        );
        for item in &self.attachments {
            bytes = bytes
                .saturating_add(item.category.capacity())
                .saturating_add(item.name.capacity())
                .saturating_add(item.media_type.as_ref().map_or(0, String::capacity));
        }
        bytes
    }
}

pub(super) fn write_message(
    connection: &Connection,
    record: &MessageRecord,
) -> Result<(), RchCoreError> {
    let queue = message_queue_projection(record);
    let mut columns = vec![
        ("message_id", sql_text(&record.message_id)),
        ("delivery_state", sql_text(&queue.delivery_state)),
        ("dispatch_status", sql_text(&queue.dispatch_status)),
        (
            "next_attempt_at_ts_ms",
            queue
                .next_attempt_at_ts_ms
                .map_or(SqlValue::Null, SqlValue::Integer),
        ),
        ("attempts", SqlValue::Integer(queue.attempts)),
        ("priority", SqlValue::Integer(queue.priority)),
        ("batch_id", sql_optional_text(queue.batch_id.as_deref())),
        ("created_ts_ms", SqlValue::Integer(queue.created_ts_ms)),
    ];
    columns.extend(super::sqlite_command_projections::columns(
        "rch_messages",
        record,
    )?);
    for (name, value) in &mut columns {
        if *name == "cache_activity_ts_ms" {
            *value = SqlValue::Integer(super::utc_now_ms());
        }
    }
    let assignments = columns
        .iter()
        .map(|(name, _)| format!("{name}=excluded.{name}"))
        .chain(["payload=excluded.payload".to_string()])
        .collect::<Vec<_>>()
        .join(",");
    let names = columns
        .iter()
        .map(|(name, _)| *name)
        .chain(["payload"])
        .collect::<Vec<_>>()
        .join(",");
    let mut values = columns
        .into_iter()
        .map(|(_, value)| value)
        .collect::<Vec<_>>();
    values.push(SqlValue::Blob(encode_msgpack(record)?));
    let placeholders = (1..=values.len())
        .map(|index| format!("?{index}"))
        .collect::<Vec<_>>()
        .join(",");
    connection.execute(
        &format!("INSERT INTO rch_messages({names}) VALUES({placeholders}) ON CONFLICT(message_id COLLATE NOCASE) DO UPDATE SET {assignments}"),
        params_from_iter(values),
    )?;
    Ok(())
}

/// Filters preserve the existing chat API's exact string comparisons.
#[derive(Default)]
pub struct ChatHistoryFilter<'a> {
    pub direction: Option<&'a str>,
    pub topic_id: Option<&'a str>,
    pub destination: Option<&'a str>,
    pub source: Option<&'a str>,
}
impl RchSqliteStore {
    pub fn message_by_id(&self, id: &str) -> Result<Option<MessageRecord>, RchCoreError> {
        use rusqlite::OptionalExtension;
        let payload: Option<Vec<u8>> = self
            .connection
            .query_row(
                "SELECT payload FROM rch_messages WHERE message_id=?1 COLLATE NOCASE",
                [id],
                |row| row.get(0),
            )
            .optional()?;
        payload.as_deref().map(decode_msgpack).transpose()
    }
    pub fn chat_history(
        &self,
        filter: &ChatHistoryFilter<'_>,
        limit: usize,
    ) -> Result<Vec<MessageRecord>, RchCoreError> {
        let mut sql = "SELECT payload FROM rch_messages WHERE chat_visible=1".to_string();
        let mut values = Vec::new();
        for (column, value) in [
            ("direction", filter.direction),
            ("topic_id", filter.topic_id),
            ("destination", filter.destination),
            ("sender", filter.source),
        ] {
            if let Some(value) = value {
                values.push(SqlValue::Text(value.into()));
                write!(&mut sql, " AND {column}=?{}", values.len())
                    .map_err(|e| RchCoreError::Encode(e.to_string()))?;
            }
        }
        // Stable descending timestamp sort over the former ascending-id presentation vector.
        values.push(SqlValue::Integer(sqlite_u64(
            u64::try_from(limit).map_err(|e| RchCoreError::Encode(e.to_string()))?,
        )?));
        write!(
            &mut sql,
            " ORDER BY created_ts_ms DESC,id ASC LIMIT ?{}",
            values.len()
        )
        .map_err(|e| RchCoreError::Encode(e.to_string()))?;
        let mut query = self.connection.prepare(&sql)?;
        let rows = query.query_map(params_from_iter(values), |row| row.get::<_, Vec<u8>>(0))?;
        rows.map(|row| decode_msgpack(&row?)).collect()
    }

    /// Active dispatch operations are durable, whether or not their parent is resident.
    pub fn message_history_counts(&self) -> Result<(usize, usize), RchCoreError> {
        let history = self.row_count("rch_messages")?;
        let active = self.connection.query_row(
            "SELECT COUNT(*) FROM rch_broker_dispatch WHERE state IN ('pending','admitted')",
            [],
            |row| sqlite_read_usize(row, 0),
        )?;
        Ok((history, active))
    }
    pub fn recent_messages(&self) -> Result<Vec<MessageRecord>, RchCoreError> {
        let mut query=self.connection.prepare("SELECT id,payload,resident_bytes FROM rch_messages WHERE resident_bytes<=?1 AND cache_activity_ts_ms>=?3 ORDER BY created_ts_ms DESC,id DESC LIMIT ?2")?;
        let mut rows = query.query(params![
            sqlite_u64(RECENT_MESSAGE_BYTES as u64)?,
            sqlite_u64(RECENT_MESSAGE_COUNT as u64)?,
            super::utc_now_ms().saturating_sub(RECENT_MESSAGE_IDLE_MS)
        ])?;
        let mut bytes = 0_usize;
        let mut messages = Vec::new();
        while let Some(row) = rows.next()? {
            let projected = sqlite_read_usize(row, 2)?;
            if bytes.saturating_add(projected) > RECENT_MESSAGE_BYTES {
                break;
            }
            let payload: Vec<u8> = row.get(1)?;
            if payload.len() > RECENT_MESSAGE_BYTES {
                continue;
            }
            let message: MessageRecord = decode_msgpack(&payload)?;
            let retained = message.estimated_resident_bytes();
            if bytes.saturating_add(retained) > RECENT_MESSAGE_BYTES {
                break;
            }
            bytes = bytes.saturating_add(retained);
            messages.push((row.get::<_, i64>(0)?, message));
        }
        messages.sort_by_key(|(id, _)| *id);
        Ok(messages.into_iter().map(|(_, message)| message).collect())
    }
}
