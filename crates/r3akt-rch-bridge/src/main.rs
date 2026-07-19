#![cfg_attr(
    not(test),
    deny(
        clippy::expect_used,
        clippy::let_underscore_must_use,
        clippy::panic,
        clippy::unwrap_used
    )
)]

use std::env;
use std::io::{self, Read};

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let mut db_path = ":memory:".to_string();
    let mut reticulumd_rpc: Option<String> = None;
    while let Some(arg) = args.next() {
        match (arg.as_str(), args.next()) {
            ("--db", Some(path)) => db_path = path,
            ("--reticulumd-rpc", Some(endpoint)) => reticulumd_rpc = Some(endpoint),
            _ => return Err(format!("unsupported argument {arg}").into()),
        }
    }
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let output = r3akt_rch_bridge::handle_json_request_with_sqlite_or_reticulumd(
        &db_path,
        reticulumd_rpc.as_deref(),
        &input,
    )?;
    println!("{output}");
    Ok(())
}
