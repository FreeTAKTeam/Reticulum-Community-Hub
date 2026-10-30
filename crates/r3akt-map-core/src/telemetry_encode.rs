//! Canonical Telemeter encoder. Speeds on the Sideband/Pyxis wire are km/h.
//! Columba 2.2.6 uses m/s in the same slot; adapters must select that profile
//! explicitly because the packet carries no unit discriminator.

use serde::{Serialize, Serializer, ser::SerializeMap};

/// A location in metres, degrees, km/h and epoch seconds (source fix time).
#[derive(Debug, Clone, Copy)]
pub struct Location {
    pub latitude: f64,
    pub longitude: f64,
    pub altitude: f64,
    pub speed: f64,
    pub bearing: f64,
    pub accuracy: f64,
    pub updated_at_s: u64,
}

struct Bytes(Vec<u8>);
impl Serialize for Bytes {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_bytes(&self.0)
    }
}

fn scaled(value: f64, scale: f64, min: i64, max: i64) -> Result<i64, &'static str> {
    let value = (value * scale).round();
    // Decimal parsing avoids saturating casts silently changing an invalid fix.
    let value = value
        .to_string()
        .parse::<i64>()
        .map_err(|_| "invalid telemetry reading")?;
    if !(min..=max).contains(&value) {
        return Err("telemetry reading out of range");
    }
    Ok(value)
}

fn signed(value: f64, scale: f64) -> Result<Bytes, &'static str> {
    let value = scaled(value, scale, i64::from(i32::MIN), i64::from(i32::MAX))?;
    Ok(Bytes(
        i32::try_from(value)
            .map_err(|_| "invalid signed reading")?
            .to_be_bytes()
            .to_vec(),
    ))
}

/// Encode the numeric sensor map carried as binary in LXMF field 0x02.
/// Missing location is permitted for battery-only SOS telemetry. Battery is
/// percent, not a fraction. Sensor time and location time remain independent.
///
/// # Errors
/// Rejects non-finite/out-of-range readings instead of wrapping or saturating.
pub fn encode(
    timestamp_s: u64,
    location: Option<Location>,
    battery: Option<(f64, bool)>,
) -> Result<Vec<u8>, &'static str> {
    encode_with_information(timestamp_s, location, battery, None)
}

/// Encode standard sensors plus Sideband's Information sensor (0x0f).
///
/// # Errors
/// Rejects invalid sensor readings or timestamps.
pub fn encode_with_information(
    timestamp_s: u64,
    location: Option<Location>,
    battery: Option<(f64, bool)>,
    information: Option<&str>,
) -> Result<Vec<u8>, &'static str> {
    if timestamp_s >= 253_402_300_800 || location.is_some_and(|l| l.updated_at_s >= 253_402_300_800)
    {
        return Err("invalid telemetry timestamp");
    }
    let location = location
        .map(|l| {
            if !(-90.0..=90.0).contains(&l.latitude) || !(-180.0..=180.0).contains(&l.longitude) {
                return Err("invalid telemetry coordinates");
            }
            let speed = u32::try_from(scaled(l.speed, 100.0, 0, i64::from(u32::MAX))?)
                .map_err(|_| "invalid speed")?;
            let accuracy = u16::try_from(scaled(l.accuracy, 100.0, 0, i64::from(u16::MAX))?)
                .map_err(|_| "invalid accuracy")?;
            Ok((
                signed(l.latitude, 1_000_000.0)?,
                signed(l.longitude, 1_000_000.0)?,
                signed(l.altitude, 100.0)?,
                Bytes(speed.to_be_bytes().to_vec()),
                signed(l.bearing, 100.0)?,
                Bytes(accuracy.to_be_bytes().to_vec()),
                l.updated_at_s,
            ))
        })
        .transpose()?;
    if battery.is_some_and(|(percent, _)| !(0.0..=100.0).contains(&percent)) {
        return Err("invalid battery percentage");
    }
    let mut bytes = Vec::new();
    let mut serializer = rmp_serde::Serializer::new(&mut bytes);
    let mut map = (&mut serializer)
        .serialize_map(Some(
            1 + usize::from(location.is_some())
                + usize::from(battery.is_some())
                + usize::from(information.is_some()),
        ))
        .map_err(|_| "telemetry encoding failed")?;
    map.serialize_entry(&1_u8, &timestamp_s)
        .map_err(|_| "telemetry encoding failed")?;
    if let Some(location) = location {
        map.serialize_entry(&2_u8, &location)
            .map_err(|_| "telemetry encoding failed")?;
    }
    if let Some(battery) = battery {
        map.serialize_entry(&4_u8, &battery)
            .map_err(|_| "telemetry encoding failed")?;
    }
    if let Some(information) = information {
        map.serialize_entry(&15_u8, information)
            .map_err(|_| "telemetry encoding failed")?;
    }
    map.end().map_err(|_| "telemetry encoding failed")?;
    Ok(bytes)
}
