//! Mission Library RPP sidecar (RCH #355). RCH's LXMF traffic goes through
//! reticulumd; RPP needs Links and Resources, so this optional sidecar runs
//! its own RNS transport, connected over TCP to the node named by
//! `RCH_RPP_TCP` (`host:port`), with a persisted identity next to the
//! database. It serves Packages that `mission.library.item.fetch` prepared,
//! only to the identities it granted.
use super::{AppState, RchSqliteStore};
use rns_transport::identity::PrivateIdentity;
use rns_transport::iface::tcp_client::TcpClient;
use rns_transport::transport::{Transport, TransportConfig};
use rpp_core::rns::system_clock;
use rpp_core::rns_share::{ShareNode, SharedPackage};
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

const IDENTITY_FILE: &str = "rch_rpp_identity";

pub(crate) struct LibraryRpp {
    pub(crate) node: Arc<ShareNode>,
    handle: tokio::runtime::Handle,
    served: Mutex<HashSet<[u8; 16]>>,
}

// shortcut: one sidecar per process (RCH runs one hub per process); move it
// into AppState if several hubs ever share a process.
static LIBRARY_RPP: OnceLock<LibraryRpp> = OnceLock::new();

pub(crate) fn library_rpp() -> Option<&'static LibraryRpp> {
    LIBRARY_RPP.get()
}

pub(crate) fn shared_package(
    token: &[u8],
    manifest: Vec<u8>,
    publication: Vec<u8>,
) -> Option<SharedPackage> {
    Some(SharedPackage {
        package_token: token.try_into().ok()?,
        manifest,
        publication,
    })
}

impl LibraryRpp {
    /// Makes a prepared Package reachable once; later calls only grant.
    pub(crate) fn serve(&'static self, shared: SharedPackage, path: PathBuf, recipient: [u8; 16]) {
        self.node.allow(&shared, recipient);
        let destination = self.node.package_destination(&shared);
        let first = self
            .served
            .lock()
            .map(|mut set| set.insert(destination))
            .unwrap_or(false);
        if first {
            self.handle.spawn(async move {
                if let Err(error) = self.node.serve(&shared, path, [recipient]).await {
                    eprintln!("library rpp: serving package failed: {error}");
                }
            });
        }
    }
}

fn load_identity(path: &Path) -> std::io::Result<PrivateIdentity> {
    if let Ok(bytes) = std::fs::read(path) {
        return PrivateIdentity::from_private_key_bytes(&bytes)
            .map_err(|error| std::io::Error::other(format!("{error:?}")));
    }
    let identity = PrivateIdentity::new_from_rand(rand_core::OsRng);
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    std::os::unix::fs::OpenOptionsExt::mode(&mut options, 0o600);
    std::io::Write::write_all(&mut options.open(path)?, &identity.to_private_key_bytes())?;
    Ok(identity)
}

/// Starts the sidecar when `RCH_RPP_TCP` is set and the hub has a database.
pub(crate) fn spawn_library_rpp(state: AppState) -> Option<tokio::task::JoinHandle<()>> {
    let endpoint = std::env::var("RCH_RPP_TCP")
        .ok()
        .filter(|value| !value.trim().is_empty())?;
    let database = state.sqlite_path.as_deref().map(PathBuf::from)?;
    Some(tokio::spawn(async move {
        let identity_path = database
            .parent()
            .unwrap_or(Path::new("."))
            .join(IDENTITY_FILE);
        let identity = match load_identity(&identity_path) {
            Ok(identity) => identity,
            Err(error) => {
                eprintln!("library rpp: identity {}: {error}", identity_path.display());
                return;
            }
        };
        let transport = Arc::new(Transport::new(TransportConfig::new(
            "rch-library",
            &identity,
            false,
        )));
        transport.iface_manager().lock().await.spawn(
            TcpClient::new(endpoint.trim().to_string()),
            TcpClient::spawn,
        );
        let node = ShareNode::start(transport, identity, system_clock, |_| {}).await;
        let rpp = LIBRARY_RPP.get_or_init(|| LibraryRpp {
            node,
            handle: tokio::runtime::Handle::current(),
            served: Mutex::default(),
        });
        // Grants are per fetch; a REM fetching again after restart is re-granted.
        let packages = RchSqliteStore::open_read_only(&database)
            .and_then(|store| store.library_rpp_packages());
        for package in packages.unwrap_or_default() {
            let Some(shared) = shared_package(
                &package.package_token,
                package.manifest,
                package.publication,
            ) else {
                continue;
            };
            let path = RchSqliteStore::open_read_only(&database)
                .ok()
                .and_then(|store| {
                    store
                        .load_file_attachment(package.file_id, "file")
                        .ok()
                        .flatten()
                        .or_else(|| {
                            store
                                .load_file_attachment(package.file_id, "image")
                                .ok()
                                .flatten()
                        })
                })
                .map(|record| PathBuf::from(record.path));
            if let Some(path) = path
                && rpp
                    .served
                    .lock()
                    .map(|mut set| set.insert(rpp.node.package_destination(&shared)))
                    .unwrap_or(false)
                && let Err(error) = rpp.node.serve(&shared, path, []).await
            {
                eprintln!(
                    "library rpp: republishing file {} failed: {error}",
                    package.file_id
                );
            }
        }
        eprintln!(
            "library rpp: serving as {}",
            hex::encode(rpp.node.me().hash())
        );
    }))
}

/// Installs a sidecar on an offline transport, for command tests.
#[cfg(test)]
pub(crate) async fn install_for_tests() -> &'static LibraryRpp {
    let identity = PrivateIdentity::new_from_rand(rand_core::OsRng);
    let transport = Arc::new(Transport::new(TransportConfig::new(
        "rch-library-test",
        &identity,
        false,
    )));
    let node = ShareNode::start(transport, identity, system_clock, |_| {}).await;
    LIBRARY_RPP.get_or_init(|| LibraryRpp {
        node,
        handle: tokio::runtime::Handle::current(),
        served: Mutex::default(),
    })
}
