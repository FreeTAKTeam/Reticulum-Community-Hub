/**
 * Marker icons are rasterized into an ICON_RASTER_SIZE square and registered with
 * ICON_PIXEL_RATIO, so `icon-size: 1` draws them at 24 CSS px whatever the source
 * SVG's intrinsic size (MDI SVGs have none, so browsers would otherwise guess).
 */
export const ICON_RASTER_SIZE = 48;
export const ICON_PIXEL_RATIO = 2;
const ICON_SIZE_MIN = 0.75; // 18 px when zoomed out
const ICON_SIZE_MAX = 1.25; // 30 px at street level and closer
const ICON_SIZE_MIN_ZOOM = 3;
const ICON_SIZE_MAX_ZOOM = 15;

/** Icon scale for a zoom level: grows gently with zoom and stays within 18-30 px. */
export const resolveIconSize = (zoom: number) => {
  const progress = (zoom - ICON_SIZE_MIN_ZOOM) / (ICON_SIZE_MAX_ZOOM - ICON_SIZE_MIN_ZOOM);
  const clamped = Math.min(1, Math.max(0, progress));
  return ICON_SIZE_MIN + (ICON_SIZE_MAX - ICON_SIZE_MIN) * clamped;
};

export const resolveClusterRadius = (zoom: number) => {
  if (zoom <= 3) {
    return 220;
  }
  if (zoom <= 4.5) {
    return 180;
  }
  if (zoom <= 6) {
    return 140;
  }
  if (zoom <= 7.5) {
    return 110;
  }
  if (zoom <= 9) {
    return 80;
  }
  if (zoom <= 11) {
    return 55;
  }
  return 35;
};
