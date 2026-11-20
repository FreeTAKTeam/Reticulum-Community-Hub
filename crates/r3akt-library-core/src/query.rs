//! Filters, pagination and mission-scoped rights, shared by every surface
//! that lists the catalog (RCH REST, RCH LXMF, REM local).

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::item::{ItemKind, LibraryItem, Source};

pub const DEFAULT_PER_PAGE: u32 = 20;
/// Bounded so one LXMF result stays small; metadata only.
pub const MAX_PER_PAGE: u32 = 50;
pub const MAX_SEARCH_BYTES: usize = 128;

/// A caller right over Library content, always evaluated per mission (or
/// globally for items with no mission). Knowing a hash or URL grants none.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Right {
    Read,
    Publish,
    Forward,
}

impl Right {
    /// The RCH operation that grants this right.
    #[must_use]
    pub fn operation(self) -> &'static str {
        match self {
            Self::Read => "mission.content.read",
            // Forwarding re-publishes content to others, so it needs write.
            Self::Publish | Self::Forward => "mission.content.write",
        }
    }
}

/// True when `authorize(mission, right)` grants the right on at least one of
/// the item's missions, or globally (`None`) for an item with no mission.
pub fn permits(
    item: &LibraryItem,
    right: Right,
    authorize: &mut impl FnMut(Option<&str>, Right) -> bool,
) -> bool {
    if item.mission_uids.is_empty() {
        return authorize(None, right);
    }
    item.mission_uids
        .iter()
        .any(|mission| authorize(Some(mission), right))
}

#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct LibraryQuery {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<ItemKind>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<Source>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mission_uid: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub search: Option<String>,
    /// 1-based.
    #[serde(default = "first_page")]
    pub page: u32,
    #[serde(default = "default_per_page")]
    pub per_page: u32,
}

fn first_page() -> u32 {
    1
}

fn default_per_page() -> u32 {
    DEFAULT_PER_PAGE
}

/// One page of authorized, filtered items, newest first.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LibraryPage {
    pub items: Vec<LibraryItem>,
    pub page: u32,
    pub per_page: u32,
    pub total: u64,
    pub has_next: bool,
}

impl LibraryQuery {
    /// The first page with default size and no filters.
    #[must_use]
    pub fn default_page() -> Self {
        Self {
            page: 1,
            per_page: DEFAULT_PER_PAGE,
            ..Self::default()
        }
    }

    /// Parses command args (`kind`, `source`, `mission_uid`, `search`,
    /// `page`, `per_page`); unknown keys such as transport metadata are ignored.
    ///
    /// # Errors
    /// Returns the reason the args are out of bounds or malformed.
    pub fn from_args(args: &Value) -> Result<Self, String> {
        let pick = |key: &str| args.get(key).filter(|value| !value.is_null()).cloned();
        let mut query = Self {
            page: 1,
            per_page: DEFAULT_PER_PAGE,
            ..Self::default()
        };
        if let Some(kind) = pick("kind") {
            query.kind =
                Some(serde_json::from_value(kind).map_err(|_| "kind must be file or image")?);
        }
        if let Some(source) = pick("source") {
            query.source = Some(
                serde_json::from_value(source).map_err(|_| "source must be local, rch or peer")?,
            );
        }
        if let Some(mission) = pick("mission_uid") {
            let mission = mission.as_str().map(str::trim).filter(|v| !v.is_empty());
            query.mission_uid = Some(mission.ok_or("mission_uid must be text")?.to_string());
        }
        if let Some(search) = pick("search") {
            let search = search
                .as_str()
                .ok_or("search must be text")?
                .trim()
                .to_string();
            query.search = (!search.is_empty()).then_some(search);
        }
        let number = |key: &str, default: u32| -> Result<u32, String> {
            match pick(key) {
                None => Ok(default),
                Some(value) => value
                    .as_u64()
                    .and_then(|v| u32::try_from(v).ok())
                    .ok_or_else(|| format!("{key} must be a positive integer")),
            }
        };
        query.page = number("page", 1)?;
        query.per_page = number("per_page", DEFAULT_PER_PAGE)?;
        query.validate()?;
        Ok(query)
    }

    /// # Errors
    /// Returns the reason a bound is violated.
    pub fn validate(&self) -> Result<(), String> {
        if self.page == 0 {
            return Err("page starts at 1".into());
        }
        if self.per_page == 0 || self.per_page > MAX_PER_PAGE {
            return Err(format!("per_page must be 1..={MAX_PER_PAGE}"));
        }
        if self
            .search
            .as_ref()
            .is_some_and(|s| s.len() > MAX_SEARCH_BYTES)
        {
            return Err(format!("search is limited to {MAX_SEARCH_BYTES} bytes"));
        }
        Ok(())
    }

    fn matches(&self, item: &LibraryItem) -> bool {
        self.kind.is_none_or(|kind| item.kind == kind)
            && self.source.is_none_or(|source| item.source == source)
            && self
                .mission_uid
                .as_ref()
                .is_none_or(|uid| item.mission_uids.contains(uid))
            && self
                .search
                .as_ref()
                .is_none_or(|needle| item.name.to_lowercase().contains(&needle.to_lowercase()))
    }

    /// Authorizes before filtering, so unauthorized items never affect the
    /// totals a caller sees; then filters, sorts newest first and pages.
    pub fn apply(
        &self,
        items: impl IntoIterator<Item = LibraryItem>,
        mut authorize: impl FnMut(Option<&str>, Right) -> bool,
    ) -> LibraryPage {
        let mut visible: Vec<LibraryItem> = items
            .into_iter()
            .filter(|item| permits(item, Right::Read, &mut authorize) && self.matches(item))
            .collect();
        visible.sort_by(|a, b| {
            b.created_ts_ms
                .cmp(&a.created_ts_ms)
                .then_with(|| a.item_id.cmp(&b.item_id))
        });
        let total = visible.len() as u64;
        let per_page = self.per_page.max(1) as usize;
        let start = (self.page.max(1) as usize - 1).saturating_mul(per_page);
        let items: Vec<LibraryItem> = visible.into_iter().skip(start).take(per_page).collect();
        let has_next = (start + items.len()) < usize::try_from(total).unwrap_or(usize::MAX);
        LibraryPage {
            items,
            page: self.page,
            per_page: self.per_page,
            total,
            has_next,
        }
    }
}
