use std::env;
use std::path::PathBuf;

use r3akt_rch_core::python_migration::{import_legacy_config_settings, migrate_python_database};

#[derive(Debug, Default)]
struct Args {
    legacy_db: Option<PathBuf>,
    target_db: Option<PathBuf>,
    legacy_config: Option<PathBuf>,
    report_json: bool,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args = parse_args(env::args().skip(1))?;
    let legacy_db = args.legacy_db.clone().ok_or("--legacy-db is required")?;
    let target_db = args.target_db.clone().ok_or("--target-db is required")?;
    let report_json = args.report_json;
    let report = migrate_from_args(args)?;
    if report_json {
        println!("{}", serde_json::to_string_pretty(&report)?);
    } else {
        println!(
            "Migrated Python RCH database {} -> {}",
            legacy_db.display(),
            target_db.display()
        );
        for (table, count) in &report.rows {
            println!("{table}: {count}");
        }
        for warning in &report.warnings {
            eprintln!("warning: {warning}");
        }
    }
    Ok(())
}

fn migrate_from_args(
    args: Args,
) -> Result<r3akt_rch_core::python_migration::PythonMigrationReport, Box<dyn std::error::Error>> {
    let legacy_db = args.legacy_db.ok_or("--legacy-db is required")?;
    let target_db = args.target_db.ok_or("--target-db is required")?;
    let mut report = migrate_python_database(&legacy_db, &target_db)?;
    if let Some(config_path) = args.legacy_config {
        let count = import_legacy_config_settings(&target_db, &config_path)?;
        report.rows.insert("config.ini".to_string(), count);
    }
    Ok(report)
}

fn parse_args<I, S>(args: I) -> Result<Args, Box<dyn std::error::Error>>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let mut parsed = Args::default();
    let mut iter = args.into_iter().map(Into::into);
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--legacy-db" => parsed.legacy_db = iter.next().map(PathBuf::from),
            "--target-db" => parsed.target_db = iter.next().map(PathBuf::from),
            "--legacy-config" => parsed.legacy_config = iter.next().map(PathBuf::from),
            "--report-json" => parsed.report_json = true,
            "--help" | "-h" => {
                print_usage();
                std::process::exit(0);
            }
            other => return Err(format!("unknown argument '{other}'").into()),
        }
    }
    Ok(parsed)
}

fn print_usage() {
    println!(
        "Usage: migrate_python_rch --legacy-db <rth_api.sqlite> --target-db <rch_state.sqlite3> [--legacy-config <config.ini>] [--report-json]"
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;
    use uuid::Uuid;

    #[test]
    fn parses_required_paths() {
        let args = parse_args([
            "--legacy-db",
            "RCH_Store/rth_api.sqlite",
            "--target-db",
            "RTH_Store/rch_state.sqlite3",
            "--legacy-config",
            "RCH_Store/config.ini",
            "--report-json",
        ])
        .expect("args");
        assert_eq!(
            args.legacy_db.as_deref(),
            Some(std::path::Path::new("RCH_Store/rth_api.sqlite"))
        );
        assert!(args.report_json);
    }

    #[test]
    fn migrates_database_and_config_from_parsed_args() {
        let legacy_db = std::env::temp_dir().join(format!(
            "r3akt-python-migration-cli-legacy-{}.sqlite3",
            Uuid::new_v4()
        ));
        let target_db = std::env::temp_dir().join(format!(
            "r3akt-python-migration-cli-target-{}.sqlite3",
            Uuid::new_v4()
        ));
        let config_path = std::env::temp_dir().join(format!(
            "r3akt-python-migration-cli-config-{}.ini",
            Uuid::new_v4()
        ));
        create_cli_legacy_database(&legacy_db);
        std::fs::write(
            &config_path,
            "[server]\nlog_level = debug\n\n[migration]\npython_store = RCH_Store\n",
        )
        .expect("config");
        let args = parse_args([
            "--legacy-db",
            legacy_db.to_str().expect("legacy db"),
            "--target-db",
            target_db.to_str().expect("target db"),
            "--legacy-config",
            config_path.to_str().expect("config"),
            "--report-json",
        ])
        .expect("args");

        let report = migrate_from_args(args).expect("migration");

        assert_eq!(report.rows["topics"], 1);
        assert_eq!(report.rows["config.ini"], 2);
        let target = Connection::open(&target_db).expect("target");
        let topic_count: i64 = target
            .query_row("SELECT COUNT(*) FROM rch_topics", [], |row| row.get(0))
            .expect("topic count");
        let log_level: String = target
            .query_row(
                "SELECT setting_value FROM rch_settings WHERE setting_key = 'python_config.server.log_level'",
                [],
                |row| row.get(0),
            )
            .expect("log level");
        assert_eq!(topic_count, 1);
        assert_eq!(log_level, "debug");

        let _ = std::fs::remove_file(legacy_db);
        let _ = std::fs::remove_file(target_db);
        let _ = std::fs::remove_file(config_path);
    }

    #[test]
    fn reports_missing_required_paths_before_migrating() {
        let error = migrate_from_args(Args::default()).expect_err("missing args");

        assert_eq!(error.to_string(), "--legacy-db is required");
    }

    fn create_cli_legacy_database(path: &std::path::Path) {
        let db = Connection::open(path).expect("legacy db");
        db.execute_batch(
            r"
            CREATE TABLE topics (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                path VARCHAR NOT NULL,
                description VARCHAR,
                created_at DATETIME NOT NULL
            );
            INSERT INTO topics VALUES (
                'ops', 'Ops', '/ops', 'operations',
                '2026-05-12 10:11:12.000000'
            );
            ",
        )
        .expect("legacy schema");
    }
}
