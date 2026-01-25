import { ref } from "vue";
import { defineStore } from "pinia";
import { loadJson } from "../utils/storage";
import { saveJson } from "../utils/storage";

interface MapSettings {
  showMarkerLabels: boolean;
  mapView?: MapView | null;
}

interface MapView {
  lat: number;
  lon: number;
  zoom: number;
}

const STORAGE_KEY = "rth-ui-map-settings";

const normalizeMapView = (value?: MapView | null): MapView | null => {
  if (!value) {
    return null;
  }
  if (
    !Number.isFinite(value.lat) ||
    !Number.isFinite(value.lon) ||
    !Number.isFinite(value.zoom)
  ) {
    return null;
  }
  return {
    lat: value.lat,
    lon: value.lon,
    zoom: value.zoom
  };
};

export const useMapSettingsStore = defineStore("map-settings", () => {
  const stored = loadJson<MapSettings>(STORAGE_KEY, {
    showMarkerLabels: true,
    mapView: null
  });

  const showMarkerLabels = ref<boolean>(stored.showMarkerLabels ?? true);
  const mapView = ref<MapView | null>(normalizeMapView(stored.mapView));

  const persist = () => {
    saveJson(STORAGE_KEY, {
      showMarkerLabels: showMarkerLabels.value,
      mapView: mapView.value
    });
  };

  const setShowMarkerLabels = (value: boolean) => {
    showMarkerLabels.value = value;
    persist();
  };

  const toggleShowMarkerLabels = () => {
    setShowMarkerLabels(!showMarkerLabels.value);
  };

  const setMapView = (value: MapView | null) => {
    mapView.value = normalizeMapView(value);
    persist();
  };

  return {
    showMarkerLabels,
    mapView,
    setShowMarkerLabels,
    toggleShowMarkerLabels,
    setMapView
  };
});
