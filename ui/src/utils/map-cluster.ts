export const BASE_ICON_ZOOM = 1;

export const resolveZoomScale = (zoom: number, baseZoom: number = BASE_ICON_ZOOM) => {
  return Math.pow(1.1, zoom - baseZoom);
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
