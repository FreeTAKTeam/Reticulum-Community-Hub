import accountSvg from "@mdi/svg/svg/account.svg?raw";
import accountGroupSvg from "@mdi/svg/svg/account-group.svg?raw";
import alertSvg from "@mdi/svg/svg/alert.svg?raw";
import antennaSvg from "@mdi/svg/svg/antenna.svg?raw";
import cameraSvg from "@mdi/svg/svg/camera.svg?raw";
import carSvg from "@mdi/svg/svg/car.svg?raw";
import clipboardCheckSvg from "@mdi/svg/svg/clipboard-check.svg?raw";
import cloverSvg from "@mdi/svg/svg/clover.svg?raw";
import droneSvg from "@mdi/svg/svg/drone.svg?raw";
import fireSvg from "@mdi/svg/svg/fire.svg?raw";
import homeFloodSvg from "@mdi/svg/svg/home-flood.svg?raw";
import hospitalSvg from "@mdi/svg/svg/hospital.svg?raw";
import mapMarkerSvg from "@mdi/svg/svg/map-marker.svg?raw";
import officeBuildingSvg from "@mdi/svg/svg/office-building.svg?raw";
import pawSvg from "@mdi/svg/svg/paw.svg?raw";
import radarSvg from "@mdi/svg/svg/radar.svg?raw";
import radioSvg from "@mdi/svg/svg/radio.svg?raw";
import rectangleSvg from "@mdi/svg/svg/rectangle.svg?raw";
import rhombusSvg from "@mdi/svg/svg/rhombus.svg?raw";
import squareSvg from "@mdi/svg/svg/square.svg?raw";

// Restrict bundled MDI icons to known mission marker symbols.
const MDI_ICON_ALLOWLIST: Record<string, string> = {
  account: accountSvg,
  "account-group": accountGroupSvg,
  alert: alertSvg,
  antenna: antennaSvg,
  camera: cameraSvg,
  car: carSvg,
  "clipboard-check": clipboardCheckSvg,
  clover: cloverSvg,
  drone: droneSvg,
  fire: fireSvg,
  "home-flood": homeFloodSvg,
  hospital: hospitalSvg,
  "map-marker": mapMarkerSvg,
  "office-building": officeBuildingSvg,
  paw: pawSvg,
  radar: radarSvg,
  radio: radioSvg,
  rectangle: rectangleSvg,
  rhombus: rhombusSvg,
  square: squareSvg
};

const normalizeMdiName = (value: string) =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "");

export const loadMdiSvg = async (name: string) => {
  const normalized = normalizeMdiName(name);
  if (!normalized) {
    return null;
  }
  return MDI_ICON_ALLOWLIST[normalized] ?? null;
};
