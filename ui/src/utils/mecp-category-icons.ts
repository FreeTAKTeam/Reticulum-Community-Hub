import type { MapEventSeverity } from "./event-map";

// Same icon set and colours as REM's event map (apps/mobile/src/utils/mecpCategoryIcons.ts),
// as path data for a 24x24 box so Canvas Path2D can draw them; circles are written as arcs.
const ICONS: Record<string, string[]> = {
  M: ["M12 5v14", "M5 12h14", "M6 6h12v12H6z"],
  T: ["M4 18 9 7l4 7 2-4 5 8", "M8 18h8", "M11 12h2"],
  W: ["M7 17h10a4 4 0 0 0 0-8 6 6 0 0 0-11.6 2", "M8 20l2-3", "M14 20l2-3"],
  S: ["M5 9h14v10H5z", "M8 9V6h8v3", "M12 12v4", "M10 14h4"],
  P: ["M12 21s6-5.2 6-11a6 6 0 0 0-12 0c0 5.8 6 11 6 11Z", "M12 10h.01"],
  C: ["M6 8h6", "M12 8l5 5", "M7 17h10", "M4 8a2 2 0 1 0 4 0a2 2 0 1 0 -4 0", "M16 14a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"],
  R: ["m5 13 4 4L19 7", "M4 20h16"],
  D: ["M5 8h14", "M7 8v10", "M17 8v10", "m8 6 2-2", "m14 6 2-2"],
  L: ["M5 15h14", "M8 15v4", "M16 15v4", "M7 12a5 5 0 0 1 10 0"],
  X: ["M12 4 3 20h18L12 4Z", "M12 9v4", "M12 17h.01"],
  H: ["M7 12 12 7l5 5", "M8 12v7h8v-7", "M10 19v-4h4v4"],
  B: ["M12 3v4", "M12 17v4", "M4 12h4", "M16 12h4", "M8 12a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"]
};
// Events without an MECP category: a plain note.
const NOTE = ["M6 4h9l3 3v13H6z", "M9 11h6", "M9 15h6"];

/** REM's severity colours; Routine and non-MECP events are grey there too. */
export const EVENT_SEVERITY_COLORS: Record<MapEventSeverity, string> = {
  mayday: "#d9534f",
  urgent: "#e7b55a",
  safety: "#5cb85c",
  routine: "#8a9ba8",
  none: "#8a9ba8"
};

/** Map image id for an event icon; categories without an icon get the note. */
export const eventIconId = (category: string, severity: MapEventSeverity): string =>
  `rch-event-${ICONS[category] ? category : "note"}-${severity}`;

export const EVENT_ICON_PIXEL_RATIO = 2;
const SIZE = 44;

/**
 * Square badge like REM's map marker: dark tile, severity border and stroke icon,
 * plus a "!" on Mayday so severity is not shown by colour alone. Null without a 2D canvas.
 */
export function drawEventIcon(id: string): ImageData | null {
  const match = /^rch-event-(\w+)-(\w+)$/.exec(id);
  if (!match) return null;
  const paths = ICONS[match[1]] ?? NOTE;
  const severity = match[2] as MapEventSeverity;
  const color = EVENT_SEVERITY_COLORS[severity] ?? EVENT_SEVERITY_COLORS.none;
  const scale = EVENT_ICON_PIXEL_RATIO;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = SIZE * scale;
  let context: CanvasRenderingContext2D | null = null;
  try {
    context = canvas.getContext("2d");
  } catch {
    return null;
  }
  if (!context || typeof Path2D === "undefined") return null;
  context.scale(scale, scale);
  // Tile 34x34 at (5,5), leaving room for the Mayday badge at the top right.
  context.beginPath();
  context.roundRect(5, 5, 34, 34, 9);
  context.fillStyle = "#071025";
  context.fill();
  context.lineWidth = 2;
  context.strokeStyle = color;
  context.stroke();
  context.save();
  context.translate(12, 12);
  context.scale(20 / 24, 20 / 24);
  context.lineWidth = 1.9 * (24 / 20);
  context.lineCap = "round";
  context.lineJoin = "round";
  for (const path of paths) context.stroke(new Path2D(path));
  context.restore();
  if (severity === "mayday") {
    context.beginPath();
    context.arc(37, 7, 7, 0, Math.PI * 2);
    context.fillStyle = color;
    context.fill();
    context.fillStyle = "#071025";
    context.font = "900 11px sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText("!", 37, 7.5);
  }
  return context.getImageData(0, 0, canvas.width, canvas.height);
}
