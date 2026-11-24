//! Shared R3AKT Library catalog for RCH and REM.
//!
//! One contract for Library metadata: the item record and its distinct
//! identities (local item ID, RCH legacy `FileID`, RDO Package/File
//! Destinations, manifest hash, content SHA-256), source and availability,
//! query filters and pagination, and mission/TEAM-scoped read, publish and
//! forward rights. Storage, HTTP, LXMF transport and UI stay in each
//! application. Bytes never travel in these records.

pub mod item;
pub mod query;

pub use item::{Availability, ItemKind, LibraryItem, RppReference, Source, validate_name};
pub use query::{LibraryPage, LibraryQuery, Right, permits};

/// Lists authorized catalog metadata. Args are a [`LibraryQuery`].
pub const LIST_COMMAND: &str = "mission.library.list";
/// Returns one authorized item by `item_id` or `file_id`.
pub const ITEM_GET_COMMAND: &str = "mission.library.item.get";
/// Asks the hub to make one authorized item available over RPP; the result
/// carries its Package Destination. Args: `item_id` or `file_id`, and the
/// caller's `rpp_identity` (identity hash, checked against the LXMF source).
pub const ITEM_FETCH_COMMAND: &str = "mission.library.item.fetch";
/// Links an item to a mission (publish right on that mission).
pub const ITEM_LINK_COMMAND: &str = "mission.library.item.link";

/// RCH catalog ID for a legacy attachment.
#[must_use]
pub fn rch_item_id(file_id: u64) -> String {
    format!("rch:{file_id}")
}

/// The legacy `FileID` inside an RCH catalog ID.
#[must_use]
pub fn rch_file_id(item_id: &str) -> Option<u64> {
    item_id.strip_prefix("rch:")?.parse().ok()
}
