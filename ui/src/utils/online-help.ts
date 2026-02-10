export type HelpProfile = {
  title: string;
  fileName: string;
};

export type HelpScreen = {
  path: string;
  title: string;
  fileName: string;
};

export const HELP_BY_PATH: Record<string, HelpProfile> = {
  "/": { title: "Mission Control // Dashboard", fileName: "dashboard.txt" },
  "/webmap": { title: "Atlas Operations // WebMap", fileName: "webmap.txt" },
  "/topics": { title: "Signal Matrix // Topics", fileName: "topics.txt" },
  "/files": { title: "Asset Vault // Files", fileName: "files.txt" },
  "/chat": { title: "Comms Array // Communications", fileName: "chat.txt" },
  "/users": { title: "Identity Grid // Users", fileName: "users.txt" },
  "/configure": { title: "Node Tuning // Configure", fileName: "configure.txt" },
  "/about": { title: "System Intel // About", fileName: "about.txt" },
  "/connect": { title: "Link Uplink // Connect", fileName: "connect.txt" }
};

export const FALLBACK_HELP: HelpProfile = {
  title: "Online Help",
  fileName: "dashboard.txt"
};

export const HELP_SCREENS: HelpScreen[] = Object.entries(HELP_BY_PATH).map(([path, profile]) => ({
  path,
  title: profile.title,
  fileName: profile.fileName
}));

export const getHelpProfileForPath = (path: string): HelpProfile => HELP_BY_PATH[path] ?? FALLBACK_HELP;

export const resolveHelpUrl = (fileName: string): string => {
  const base = import.meta.env.BASE_URL ?? "/";
  const normalizedBase = base.endsWith("/") ? base : `${base}/`;
  return `${normalizedBase}help/${fileName}`;
};
