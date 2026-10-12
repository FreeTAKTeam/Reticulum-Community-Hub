//! Stable, conversation-scoped history pages over durable message rows.
use super::{Connection, MessageRecord, RchCoreError, RchSqliteStore, decode_msgpack, params};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChatCursor {
    pub created_ts_ms: i64,
    pub row_id: i64,
}
impl ChatCursor {
    pub fn parse(value: &str) -> Result<Self, RchCoreError> {
        let (time, id) = value
            .split_once(':')
            .ok_or_else(|| RchCoreError::Decode("invalid chat cursor".into()))?;
        let created_ts_ms = time
            .parse()
            .map_err(|_| RchCoreError::Decode("invalid chat cursor timestamp".into()))?;
        let row_id = id
            .parse::<i64>()
            .map_err(|_| RchCoreError::Decode("invalid chat cursor row ID".into()))?;
        if row_id <= 0 {
            return Err(RchCoreError::Decode("invalid chat cursor row ID".into()));
        }
        Ok(Self {
            created_ts_ms,
            row_id,
        })
    }
    #[must_use]
    pub fn encode(self) -> String {
        format!("{}:{}", self.created_ts_ms, self.row_id)
    }
}

pub struct ChatConversationFilter<'a> {
    pub scope: &'a str,
    pub target: Option<&'a str>,
}
pub struct ChatHistoryPage {
    pub messages: Vec<MessageRecord>,
    pub next_cursor: Option<ChatCursor>,
}

pub(super) fn page_sql(scope: &str) -> Result<String, RchCoreError> {
    if !matches!(scope, "broadcast" | "topic" | "dm") {
        return Err(RchCoreError::InvalidPayload(
            "invalid conversation scope".into(),
        ));
    }
    // Literal predicates prove partial-index eligibility. Naming the matching index
    // prevents LIMIT estimates from choosing a global history scan for sparse peers.
    let base = |index: &str| {
        format!(
            "SELECT id,created_ts_ms,payload FROM rch_messages INDEXED BY {index} WHERE scope='{scope}' AND chat_visible=1"
        )
    };
    let cursor = " AND created_ts_ms<=?3 AND (created_ts_ms<?3 OR id>?4) ORDER BY created_ts_ms DESC,id ASC LIMIT ?5";
    match scope {
        "broadcast" => Ok(format!(
            "{}{cursor}",
            base("idx_rch_messages_scope_history")
        )),
        "topic" => Ok(format!(
            "{} AND topic_id=?2{cursor}",
            base("idx_rch_messages_topic_history")
        )),
        "dm" => Ok(format!(
            "SELECT * FROM (SELECT * FROM ({} AND chat_source=?2 AND direction='inbound'{cursor}) UNION ALL SELECT * FROM ({} AND destination=?2 AND direction='outbound'{cursor})) ORDER BY created_ts_ms DESC,id ASC LIMIT ?5",
            base("idx_rch_messages_source_history"),
            base("idx_rch_messages_destination_history")
        )),
        _ => Err(RchCoreError::InvalidPayload(
            "invalid conversation scope".into(),
        )),
    }
}
impl RchSqliteStore {
    pub fn chat_history_page(
        &self,
        filter: &ChatConversationFilter<'_>,
        cursor: Option<ChatCursor>,
        limit: usize,
    ) -> Result<ChatHistoryPage, RchCoreError> {
        let sql = page_sql(filter.scope)?;
        let cursor = cursor.unwrap_or(ChatCursor {
            created_ts_ms: i64::MAX,
            row_id: 0,
        });
        let mut query = self.connection.prepare(&sql)?;
        let limit =
            i64::try_from(limit).map_err(|error| RchCoreError::Encode(error.to_string()))?;
        let rows = query.query_map(
            params![
                filter.scope,
                filter.target,
                cursor.created_ts_ms,
                cursor.row_id,
                limit.saturating_add(1)
            ],
            |row| {
                Ok((
                    ChatCursor {
                        row_id: row.get(0)?,
                        created_ts_ms: row.get(1)?,
                    },
                    row.get::<_, Vec<u8>>(2)?,
                ))
            },
        )?;
        let mut messages = Vec::new();
        let mut last = None;
        let mut more = false;
        for row in rows {
            let (key, payload) = row?;
            if messages.len()
                >= usize::try_from(limit)
                    .map_err(|error| RchCoreError::Encode(error.to_string()))?
            {
                more = true;
                break;
            }
            messages.push(decode_msgpack(&payload)?);
            last = Some(key);
        }
        Ok(ChatHistoryPage {
            messages,
            next_cursor: if more { last } else { None },
        })
    }
}

pub(super) fn migrate_chat_scope(connection: &Connection) -> Result<(), RchCoreError> {
    for field in ["scope", "chat_source"] {
        if !super::sqlite_table_has_column(connection, "rch_messages", field)? {
            connection.execute(
                &format!("ALTER TABLE rch_messages ADD COLUMN {field} TEXT"),
                [],
            )?;
        }
    }
    // Decode one row at a time and update only scalar projections, never payload bytes.
    let mut statement = connection.prepare("SELECT id,payload FROM rch_messages ORDER BY id")?;
    let mut rows = statement.query([])?;
    while let Some(row) = rows.next()? {
        let id: i64 = row.get(0)?;
        let payload: Vec<u8> = row.get(1)?;
        let message: MessageRecord = decode_msgpack(&payload)?;
        let (scope, source) = scope_projection(&message);
        connection.execute(
            "UPDATE rch_messages SET scope=?1,chat_source=?2 WHERE id=?3",
            params![scope, source, id],
        )?;
    }
    connection.execute_batch("CREATE INDEX IF NOT EXISTS idx_rch_messages_scope_history ON rch_messages(created_ts_ms DESC,id ASC) WHERE scope='broadcast' AND chat_visible=1;
        CREATE INDEX IF NOT EXISTS idx_rch_messages_topic_history ON rch_messages(topic_id,created_ts_ms DESC,id ASC) WHERE scope='topic' AND chat_visible=1;
        CREATE INDEX IF NOT EXISTS idx_rch_messages_source_history ON rch_messages(chat_source,created_ts_ms DESC,id ASC) WHERE scope='dm' AND direction='inbound' AND chat_visible=1;
        CREATE INDEX IF NOT EXISTS idx_rch_messages_destination_history ON rch_messages(destination,created_ts_ms DESC,id ASC) WHERE scope='dm' AND direction='outbound' AND chat_visible=1;
")?;
    Ok(())
}
pub(super) fn scope_projection(message: &MessageRecord) -> (&'static str, &str) {
    let scope = match message.delivery_mode {
        super::DeliveryMode::Targeted => "dm",
        super::DeliveryMode::Fanout => "topic",
        super::DeliveryMode::Broadcast => "broadcast",
    };
    let source = message.delivery_metadata["source"]
        .as_str()
        .unwrap_or(&message.sender);
    (scope, source)
}
