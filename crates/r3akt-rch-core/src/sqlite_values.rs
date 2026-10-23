use super::RchCoreError;

pub(crate) fn sqlite_u64(value: u64) -> Result<i64, RchCoreError> {
    i64::try_from(value).map_err(|error| {
        RchCoreError::InvalidPayload(format!("SQLite integer out of range: {error}"))
    })
}

pub(crate) fn sqlite_read_u64(row: &rusqlite::Row<'_>, index: usize) -> rusqlite::Result<u64> {
    let value: i64 = row.get(index)?;
    u64::try_from(value).map_err(|error| {
        rusqlite::Error::FromSqlConversionFailure(
            index,
            rusqlite::types::Type::Integer,
            Box::new(error),
        )
    })
}

pub(crate) fn sqlite_read_usize(row: &rusqlite::Row<'_>, index: usize) -> rusqlite::Result<usize> {
    let value: i64 = row.get(index)?;
    usize::try_from(value).map_err(|error| {
        rusqlite::Error::FromSqlConversionFailure(
            index,
            rusqlite::types::Type::Integer,
            Box::new(error),
        )
    })
}
