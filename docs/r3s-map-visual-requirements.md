# R3S/1 map graphics requirements: RCH and REM

Status: **proposed visual acceptance contract**, 15 November 2026. This document specifies the graphical presentation of existing R3S/1 pose/FOV telemetry and the proposed SPI point events. It does **not** assert that the SPI feature is implemented.

Applies to:
- **RCH:** existing `/webmap` MapLibre map and `ui/src/components/map/SensorGeometryLayer.vue`.
- **REM:** existing Android/Web `TelemetryMapView.vue`, MapLibre map and `apps/mobile/src/components/map/SensorGeometryLayer.vue`.
- **Shared data authority:** `crates/r3akt-map-core` computes and validates geometry/freshness; both UIs render identical canonical projections. The SPI projection is a proposed addition.

Primary reference: the user-supplied annotated ATAK drone screenshot with a platform symbol/name, FOV wedge and bearing indicator, and a separate crosshair labeled **Sensor Point of Interest**. The screenshot establishes required visual *roles*, not exact ATAK branding, map tiles or color codes.

Related contracts: [R3S/1 telemetry already implemented in RCH](r3s-telemetry.md), [original REM specification](https://github.com/FreeTAKTeam/reticulum_mobile_emergency_management/blob/main/docs/plans/R3AKT_Sensor_Telemetry_Extension_v1.md), [proposed LXMF SPI extension](https://github.com/FreeTAKTeam/LXMF-rs/blob/docs/r3s-sensor-spi-extension/docs/contracts/r3s-sensor-telemetry-spi-v1.md).

## 1. Visual target and object relationships

The map MUST show these as distinct but related objects, when the native source data support each:

~~~
                       [SPI crosshair]  <- geographic point; may be absent
                            +
                        (optional link)
                       /  |
               .------'   |  bearing axis / centerline
              /  FOV      |
             /  sector    |
            /             |
        [UAS symbol + callsign] <- authoritative origin coordinate
~~~

This is a schematic, not a geometric calculation: the FOV is anchored on the *sensor origin*, the SPI crosshair is at its own reported/estimated geographic coordinate. The crosshair does NOT automatically coincide with the wedge tip or with the origin. An operator-designated SPI may lie outside the FOV. Multiple sensors belong to a single origin, not to separate drone positions.

### Normative graphics requirements

| ID | Requirement | Observable acceptance |
| --- | --- | --- |
| MAP-01 | **Origin symbol:** retain existing canonical R3AKT/REM tactical marker at the origin's true position, with its existing classification color, symbol and name/callsign. Do not draw a second drone icon for its sensor. | One labeled object symbol at the origin; controller/relay position not replaced by drone position |
| MAP-02 | **Boresight:** direction indicator/centerline starts at the origin and follows sensor `azimuthDeg` clockwise from **true north**, regardless of aircraft course/yaw. A distinct arrow or arrowhead remains readable on dark/light tiles. | Azimuth 0° points north, 90° east; rotating the aircraft course alone does not rotate an already world-referenced camera |
| MAP-03 | **FOV wedge:** light transparent fill and contrasting outline, bounded by `azimuthDeg ± horizontalFovDeg/2` and the existing native planar ground extent. Use the current amber default (`#e7b55a` fill at about 0.18 opacity, `#ffd789` outline/axis), subject to the app's contrast theme. | 20° camera FOV points as a 20° wedge, not a line or full circle; underlying map and symbols remain visible |
| MAP-04 | **Range rendering:** measured-target slant range drives a sector extent only through native `slantRangeM * cos(elevation)` projection. A `display-limit` is shown with a visually distinct dashed boundary/legend and *must not* read as observed target distance. If range is unknown, show heading only, no invented wedge. | Details show `Measured 500 m slant`, `Display limit 500 m`, or `Range unknown` distinctly |
| MAP-05 | **SPI crosshair:** place a recognizable precision crosshair at the SPI's own `point.lat/lon`, independent from drone, FOV extent and sensor-heading icon. Use a high-contrast crosshair with a halo (recommended cyan/white), with small `SPI` tag. It must never masquerade as a detected person/vehicle or a second drone. | Crosshair is visible and selectable at the SPI point; absent SPI creates no fabricated crosshair |
| MAP-06 | **Sensor-to-SPI association:** on selection, show a thin, *optional* dashed association line from origin to SPI, independent of the FOV direction line; label/tooltip identifies the source sensor. No forced connecting line for stale/unsynchronized data. | Selecting a crosshair identifies `originId/sensorId`; selecting another origin does not steal the SPI |
| MAP-07 | **Temporal state:** active, stale, missing-fix and unsynchronized must be visibly distinct. Stale/unsynchronized geometry is suppressed (or shown only as explicitly labeled historical data in a separate mode); do not leave a bright live wedge/crosshair behind. | Stale native projection removes live coverage immediately; status and sample age remain in details |
| MAP-08 | **Accuracy and provenance:** distinguish `source-geolocation`, `operator-designated`, `flat-ground-estimate`, `terrain-intersection`, and `accuracy unknown`. Optional uncertainty circle is only drawn for a supplied, bounded `horizontalUncertaintyM`; do not create a 0 m accuracy claim. | No auto-label `measured` for computed points; unknown accuracy has no false 0-radius circle |
| MAP-09 | **Tracking:** new origin fix moves its symbol and anchored FOV; new pose rotates/resizes the wedge; a new SPI moves its crosshair. Independent updates do not change unrelated origin or sensor state. Updates should avoid flicker and never automatically pan/zoom. | Two origins, each with several sensors, update independently |
| MAP-10 | **Map layer lifecycle:** overlays work over every supported map style, online/offline tiles, map zoom/pitch/bearing and style replacement. They respect antimeridian crossing, map wrap and cross-0° bearings. Preserve the single existing MapLibre instance. | Changing tiles/style does not lose, duplicate or multiply layers |
| MAP-11 | **Ordering:** FOV fill below origin markers, tactical map symbols, SPI crosshairs and essential labels. Sector border and centerline above the fill; selected crosshair above the centerline. Native SOS/high-priority alarms remain legible. | FOV never obscures the parent drone symbol or SOS indicator |
| MAP-12 | **Visibility:** provide global show/hide **Sensors** and **SPI**, and per-origin/per-sensor controls. Hiding the origin hides its FOV and dependent SPI without deleting state; hiding a sensor hides that sensor's FOV, heading and SPI. | Visibility toggles are independent of network publication and survive style reset |
| MAP-13 | **Selection:** clicking/tapping drone, FOV or crosshair opens the *same origin-and-sensor detail view* with appropriate focus; no default create-marker or edit-geometry action. A separate explicit action may save an SPI as a normal marker after permission checks. | Operator can select SPI without accidentally relocating the aircraft or creating a marker |
| MAP-14 | **Labels:** display origin label/callsign near source symbol, `SPI` with the origin/sensor identity on selection, and optionally numeric range/azimuth at appropriate zoom. Deconflict crowded labels; never rely on color alone. | Text readable across dark/light base maps and with multiple nearby sensors |
| MAP-15 | **Safe absence/failure:** no lat/lon fallback to (0,0), no precise FOV when native `display.geojson` is empty, no SPI when the event is absent, and no stale rendered features after snapshot/connection failure. | Failed `/Sensors` or native client projection clears live overlays and shows a visible nonblocking error |
| MAP-16 | **Video:** show only `Video available` (or `Unavailable`) and an explicitly approved user action; no automatic playback, no token-bearing URL in the map label/tooltip, and no attempt to send video via LXMF. | Map works entirely without video access and without leaking endpoint credentials |

### Geometry-type and visible-rendering verification

Shared sensor_geometry::project emits GeoJSON MultiPolygon for FOV; clip_line may emit MultiLineString at the antimeridian. Existing RCH/REM layers filter ["geometry-type"] for "Polygon" and "LineString". **These filters are not automatically defective:** MapLibre GL JS style expressions normalize MultiPolygon -> Polygon and MultiLineString -> LineString as [documented by MapLibre](https://maplibre.org/maplibre-style-spec/expressions/#geometry-type). Both applications declare MapLibre GL JS 6.x. The requirement is that the native geometry renders correctly in the actual map, confirmed with rendered-feature queries and screenshots.

Do not change filters solely because the GeoJSON source says MultiPolygon or MultiLineString. Preserve this behavior across MapLibre upgrades. Existing E2E tests assert source feature counts; they do not independently prove visible FOV fill, bearing lines and later SPI prominence.

## 2. Details / selection UI

Selecting an origin, sensor or SPI displays a panel or bottom sheet that keeps the map visible.

| Field | Presentation |
| --- | --- |
| Header | Existing origin name/callsign, kind (UAV, fixed camera, etc.) and trust/status |
| Sensor selector | Up to four sensor names; selected sensor emphasized on map |
| Sensor pose | Bearing/azimuth `° true`, elevation `°`, roll `°` |
| Optics | Horizontal and vertical FOV `°` |
| Range | `m slant` + measured-target/display-limit/unknown |
| SPI | Latitude/longitude, frame-center vs designated, source vs estimate, uncertainty or unknown |
| Time | Source sample age, position age, synchronized/stale status; do not relabel receive time as capture time |
| Optional video | Availability and explicitly approved action, never autoplay |
| Controls | Locate origin, Locate SPI (if valid), show/hide sensor, show/hide SPI |

If an origin has no current valid position, preserve its sensor in the panel but disable geographic Locate/FOV and state `Position unavailable`. If the SPI is valid while FOV is not, allow an independent SPI crosshair only when the native freshness/authorization rules allow it; never fabricate a wedge to connect it.

**Zoom/fit:** `Locate origin` centers on the origin; `Locate SPI` centers on the SPI; `Fit origin + SPI` fits both with sufficient margin for mobile sheets, when both coordinates are valid. None should run automatically on telemetry receipt. Zooming does not change the source-time semantics.

## 3. Presentation by platform

| Topic | REM Android/mobile map | RCH desktop/web map |
| --- | --- | --- |
| Entry | Existing `TelemetryMapView` and map overlay menu; no second map engine | Existing `/webmap`, sensor layer and map controls |
| Interaction | Tap targets at least 44×44 CSS px; selection opens a compact, dismissible bottom sheet; no permanent panel obstructing center of map | Click, keyboard and pointer focus; existing collapsible sensor details pane can be reused; selection highlights selected map geometry |
| Controls | Sensors and SPI toggles in existing map overlay menu; per-sensor controls within sheet/list | Sensors and SPI toggles alongside existing map controls/sensor pane; per-sensor controls in existing pane |
| Label density | Callsign and selected SPI label are priority at phone zoom; avoid constant numeric labels on small screens | More room for bearing/range/labels on selected/hovered sensor; use collision-aware placement |
| View modes | Respect existing REM dark/outdoor light themes and offline map styles | Respect existing RCH map styles and color scheme |
| Visibility persistence | Use existing local display preference mechanism, with safe defaults | Persist local user preferences without changing server-side publication rights |
| Status | Clear stale/failure indications that do not block navigation or SOS controls | Collapsible status with sample/source age and diagnostic reasons |

No application should duplicate geometry mathematics, source-time validation, SPI permissions or point/sector collision calculations in Vue. MapLibre renders the native FeatureCollection and distinct feature roles (e.g. `sensor-sector`, `sensor-axis`, `sensor-heading`, `sensor-spi`, `sensor-spi-link`, `sensor-uncertainty`) supplied by shared/native code. A role must not be inferred solely from geometry type.

## 4. Priority, acceptance and tests

**P0 – Existing FOV screenshot verification:** confirm actual fill and bearing line on both maps for native MultiPolygon/MultiLineString data, label the origin, and verify toggles, style changes and stale suppression. Adjust filters only if a reproducible runtime failure exists. This is required regardless of SPI protocol status.

**P1 – SPI visual parity:** after typed SPI event and native projection support, implement crosshair, association, native status/provenance, selection details, Locate/fit and independent SPI visibility in **both** maps. Use the same synthetic origin/sensor/SPI fixture to establish identical rendering semantics.

**P2 – Optional refinements:** selected-sensor emphasis, bounded accuracy ring, decluttering for dense UAV scenes and calibrated terrain footprint when separately available. Do not block P0/P1 on terrain modeling, video or 3D.

Acceptance tests (run for **both** REM and RCH):
1. **Annotated ATAK visual scenario:** one named UAV at position A, 20° HFOV, azimuth 0° true, range 500 m, SPI at position B: UAV symbol at A, translucent north-pointing wedge anchored at A, crosshair at B, no phantom duplicate origin. Save an actual screenshot and compare manually and/or via visual regression against a checked-in approved target rendering.
2. Sensor azimuth 90° true, aircraft course 180°: wedge still points east. Verify numeric bearing and range labels.
3. Two independent UAVs, each up to four sensors: per-sensor on/off and selection do not affect unrelated sensors.
4. Display-limit range vs measured range vs unknown range; nadir/missing fix: no misleading cone, correct status label.
5. Antimeridian crossing: native **MultiPolygon** and **MultiLineString** portions actually render on either side without a globe-spanning wedge.
6. Style switch, offline tiles, zoom, pan, rotate, resize, Android orientation change: overlays are not orphaned, duplicated or lost.
7. SPI frame-center vs designated point, reported vs estimated solution, known vs unknown uncertainty: crosshair position exact and provenance available.
8. Move origin without SPI update, and move SPI without origin update: respective state changes independently, native skew rules decide if connected display remains valid.
9. Source time older than TTL, revoked grant, deleted sensor/origin, failed RCH endpoint or REM native projection: no live wedge or SPI left behind.
10. Narrow phone viewport, outdoor light theme and keyboard navigation: origin and SPI remain distinguishable and controls accessible without blocking SOS/marker tools.

Automated tests MUST validate MapLibre rendered layer availability/feature visibility, not only `geojson.features` counts. RCH's existing `ui/e2e/sensor-geometry.spec.ts` and REM's existing `e2e/sensor-geometry.spec.ts` currently test native source features, toggles, style restoration and failure cleanup; extend them to cover rendered coverage and SPI overlay selection after implementation.

### Current implementation gap inventory (source inspected 15 November 2026)

| Feature | RCH | REM |
| --- | --- | --- |
| Native R3S origin/sensor projections | Existing | Existing |
| MapLibre FOV/heading component | Existing; pixel-level visibility requires verification | Existing; pixel-level visibility requires verification |
| Sensor detail panel + per-sensor visibility | Existing | Existing |
| SPI native projection/events/storage | Proposed, not implemented | Proposed, not implemented |
| SPI crosshair, link, labels and selection | Missing | Missing |
| Global SPI map toggle + Locate SPI | Missing | Missing |
| Actual rendered-geometry visual regression | Missing; feature-count tests exist | Missing; feature-count tests exist |
| Real drone + radio and ATAK interop qualification | Not established | Not established |

**Release decision:** no claim of ATAK-style complete sensor display until P0 visibility issues are fixed and P1 SPI visual elements are implemented and verified on both maps. This graphical requirement supplements, and does not change, R3S ownership/transport constraints.
