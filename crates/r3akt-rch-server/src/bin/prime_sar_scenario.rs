#![cfg_attr(
    not(test),
    deny(
        clippy::expect_used,
        clippy::let_underscore_must_use,
        clippy::panic,
        clippy::unwrap_used
    )
)]

#[path = "../sar_seed.rs"]
mod sar_seed;

use sar_seed::{SarSeedOptions, print_narrative_timeline, seed_sar_scenario};

#[tokio::main]
async fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let options = parse_args(std::env::args().skip(1))?;
    print_narrative_timeline();
    let summary = seed_sar_scenario(&options)?;
    println!("{}", serde_json::to_string_pretty(&summary)?);
    Ok(())
}

fn parse_args(
    mut args: impl Iterator<Item = String>,
) -> Result<SarSeedOptions, Box<dyn std::error::Error>> {
    let mut base_url = "http://127.0.0.1:8000".to_string();
    let mut api_key = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--base-url" => {
                base_url = args.next().ok_or("--base-url requires a value")?;
            }
            "--api-key" => {
                api_key = Some(args.next().ok_or("--api-key requires a value")?);
            }
            "-h" | "--help" => {
                println!(
                    "Usage: prime_sar_scenario --base-url http://127.0.0.1:8000 [--api-key KEY]"
                );
                std::process::exit(0);
            }
            other => return Err(format!("unknown argument: {other}").into()),
        }
    }
    Ok(SarSeedOptions { base_url, api_key })
}
