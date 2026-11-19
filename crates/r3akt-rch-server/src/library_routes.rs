//! `GET /Library`: the operator view of the Mission Library catalog. Same
//! projection, filters and pagination as `mission.library.list`; HTTP callers
//! are operators, so every item is visible. `/File` and `/Image` keep their
//! legacy output unchanged.
use super::{ApiError, AppState, RchSqliteStore};
use axum::Json;
use axum::extract::{Query, State};
use r3akt_library_core::LibraryQuery;
use serde_json::{Map, Value};

pub(crate) async fn list_library(
    State(state): State<AppState>,
    Query(params): Query<Map<String, Value>>,
) -> Result<Json<Value>, ApiError> {
    // Query strings arrive as text; numbers are parsed back for the shared parser.
    let args: Map<String, Value> = params
        .into_iter()
        .map(|(key, value)| {
            let number = value.as_str().and_then(|text| text.parse::<u64>().ok());
            (key, number.map_or(value, Value::from))
        })
        .collect();
    let query = LibraryQuery::from_args(&Value::Object(args)).map_err(ApiError::BadRequest)?;
    let items = match &state.sqlite_path {
        Some(path) => RchSqliteStore::open_read_only(path.as_ref())
            .and_then(|store| store.library_items())
            .map_err(|error| ApiError::Internal(error.to_string()))?,
        None => Vec::new(),
    };
    let page = query.apply(items, |_, _| true);
    serde_json::to_value(page)
        .map(Json)
        .map_err(|error| ApiError::Internal(error.to_string()))
}
