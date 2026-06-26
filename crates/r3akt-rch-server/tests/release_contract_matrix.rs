use std::collections::HashSet;
use std::path::Path;

use axum::body::Body;
use axum::http::{Method, Request, StatusCode};
use http_body_util::BodyExt;
use r3akt_rch_server::create_app;
use serde::Deserialize;
use serde_json::Value;
use tower::ServiceExt;

#[derive(Debug, Deserialize)]
struct ContractMatrix {
    contracts: Vec<Contract>,
}

#[derive(Debug, Deserialize)]
struct Contract {
    id: String,
    classification: String,
    kind: String,
    routes: Option<Vec<RouteContract>>,
    path: Option<String>,
    method: Option<String>,
    evidence: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct RouteContract {
    path: String,
    method: String,
}

#[tokio::test]
async fn release_contract_matrix_http_routes_are_exposed_by_rust_openapi() {
    let matrix = load_matrix();
    let openapi = rust_openapi().await;
    let paths = openapi["paths"].as_object().expect("openapi paths");

    for contract in matrix
        .contracts
        .iter()
        .filter(|contract| contract.kind == "http-route")
    {
        for route in contract.routes() {
            let method = route.method.to_ascii_lowercase();
            assert!(
                openapi_has_route_or_alias(paths, route.path, method.as_str()),
                "contract {} {method} {} missing from OpenAPI",
                contract.id,
                route.path
            );
        }
    }
}

#[test]
fn release_contract_matrix_classifies_python_and_rust_specific_surfaces() {
    let matrix = load_matrix();
    let mut ids = HashSet::new();
    let mut must_match_python_contracts = 0;
    let mut must_match_python_routes = 0;
    let mut rust_additive_required = 0;
    let mut intentional_difference = 0;

    for contract in &matrix.contracts {
        assert!(
            ids.insert(contract.id.as_str()),
            "duplicate id {}",
            contract.id
        );
        assert!(
            !contract.evidence.is_empty(),
            "contract {} must name release evidence",
            contract.id
        );
        match contract.classification.as_str() {
            "must-match-python" => {
                must_match_python_contracts += 1;
                must_match_python_routes += contract.routes().len();
            }
            "rust-additive-required" => rust_additive_required += 1,
            "intentional-difference" => intentional_difference += 1,
            other => panic!("unknown classification {other} for {}", contract.id),
        }
    }

    assert!(must_match_python_contracts >= 4);
    assert!(
        must_match_python_routes >= 100,
        "expected broad Python contract inventory"
    );
    assert!(
        rust_additive_required >= 6,
        "expected Rust additive release capability inventory"
    );
    assert!(
        intentional_difference >= 1,
        "expected documented intentional architecture differences"
    );
    assert!(
        matrix
            .contracts
            .iter()
            .any(|contract| contract.id == "rust-additive-rem-compatibility"),
        "REM compatibility must remain an explicit Rust release capability"
    );
}

impl Contract {
    fn routes(&self) -> Vec<RouteContractRef<'_>> {
        if let Some(routes) = self.routes.as_ref() {
            return routes
                .iter()
                .map(|route| RouteContractRef {
                    path: route.path.as_str(),
                    method: route.method.as_str(),
                })
                .collect();
        }
        self.path
            .as_deref()
            .zip(self.method.as_deref())
            .map(|(path, method)| vec![RouteContractRef { path, method }])
            .unwrap_or_default()
    }
}

struct RouteContractRef<'a> {
    path: &'a str,
    method: &'a str,
}

fn openapi_has_route_or_alias(
    paths: &serde_json::Map<String, Value>,
    route_path: &str,
    method: &str,
) -> bool {
    paths
        .get(route_path)
        .and_then(Value::as_object)
        .is_some_and(|operations| operations.get(method).is_some())
        || paths.values().any(|path_item| {
            path_item
                .get(method)
                .and_then(|operation| operation.get("x-rch-aliases"))
                .and_then(Value::as_array)
                .is_some_and(|aliases| aliases.iter().any(|alias| alias == route_path))
        })
}

fn load_matrix() -> ContractMatrix {
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
    let path = manifest
        .parent()
        .and_then(Path::parent)
        .expect("repo root")
        .join("docs/release-contract-matrix.json");
    let content = std::fs::read_to_string(&path).expect("contract matrix");
    serde_json::from_str(&content).expect("valid contract matrix")
}

async fn rust_openapi() -> Value {
    let response = create_app()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri("/openapi.json")
                .body(Body::empty())
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(response.status(), StatusCode::OK);
    let body = response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    serde_json::from_slice(&body).expect("json")
}
