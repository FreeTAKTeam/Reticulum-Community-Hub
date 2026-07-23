#![cfg_attr(
    not(test),
    deny(
        clippy::expect_used,
        clippy::let_underscore_must_use,
        clippy::panic,
        clippy::unwrap_used
    )
)]

use std::path::{Path, PathBuf};

use rns_core::destination::{DestinationName, SingleInputDestination};
use rns_core::identity::PrivateIdentity;
use serde_json::json;

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let (rch_path, daemon_path) = parse_args(std::env::args().skip(1))?;
    let rch_identity = load_identity(&rch_path)?;
    let rch_hash = rch_identity.address_hash().to_hex_string();
    let delivery =
        SingleInputDestination::new(rch_identity, DestinationName::new("lxmf", "delivery"))
            .desc
            .address_hash
            .to_hex_string();
    let daemon_identity_hash = daemon_path
        .as_deref()
        .filter(|path| path.exists())
        .map(load_identity)
        .transpose()?
        .map(|identity| identity.address_hash().to_hex_string());
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "daemon_identity_hash": daemon_identity_hash,
            "rch_identity_hash": rch_hash,
            "rch_delivery_destination": delivery,
        }))?
    );
    Ok(())
}

fn parse_args<I, S>(args: I) -> Result<(PathBuf, Option<PathBuf>), Box<dyn std::error::Error>>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let mut rch_path = None;
    let mut daemon_path = None;
    let mut args = args.into_iter().map(Into::into);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--rch-identity" => {
                rch_path = Some(PathBuf::from(
                    args.next().ok_or("--rch-identity requires a value")?,
                ));
            }
            "--daemon-identity" => {
                daemon_path = Some(PathBuf::from(
                    args.next().ok_or("--daemon-identity requires a value")?,
                ));
            }
            other => return Err(format!("unknown argument '{other}'").into()),
        }
    }
    Ok((rch_path.ok_or("--rch-identity is required")?, daemon_path))
}

fn load_identity(path: &Path) -> Result<PrivateIdentity, Box<dyn std::error::Error>> {
    let bytes = std::fs::read(path)?;
    if bytes.len() == 64 {
        return PrivateIdentity::from_private_key_bytes(bytes.as_slice())
            .map_err(|error| format!("invalid identity {}: {error:?}", path.display()).into());
    }
    let text = std::str::from_utf8(bytes.as_slice())?.trim();
    PrivateIdentity::new_from_hex_string(text)
        .map_err(|error| format!("invalid identity {}: {error:?}", path.display()).into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requires_rch_identity_path() {
        let error = parse_args(std::iter::empty::<String>()).expect_err("missing path");
        assert_eq!(error.to_string(), "--rch-identity is required");
    }
}
