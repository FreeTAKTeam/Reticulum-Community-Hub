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
  "/missions": { title: "Mission Workspace // Missions", fileName: "missions.txt" },
  "/missions/assets": { title: "Mission Workspace // Asset Registry", fileName: "missions.txt" },
  "/missions/logs": { title: "Mission Workspace // Logbook", fileName: "missions.txt" },
  "/checklists": { title: "Mission Workspace // Checklists", fileName: "missions.txt" },
  "/webmap": { title: "Atlas Operations // WebMap", fileName: "webmap.txt" },
  "/topics": { title: "Signal Matrix // Topics", fileName: "topics.txt" },
  "/files": { title: "Asset Vault // Files", fileName: "files.txt" },
  "/chat": { title: "Comms Array // Communications", fileName: "chat.txt" },
  "/users": { title: "Identity Grid // Users", fileName: "users.txt" },
  "/users/teams/members": { title: "Identity Grid // Team Roster", fileName: "users.txt" },
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

export const getHelpProfileForPath = (path: string): HelpProfile => {
  const direct = HELP_BY_PATH[path];
  if (direct) {
    return direct;
  }

  if (path.startsWith("/missions/")) {
    if (path.endsWith("/assets")) {
      return HELP_BY_PATH["/missions/assets"];
    }
    if (path.endsWith("/logs") || path.endsWith("/log-entries")) {
      return HELP_BY_PATH["/missions/logs"];
    }
    if (path.endsWith("/checklists")) {
      return HELP_BY_PATH["/checklists"];
    }
    return HELP_BY_PATH["/missions"];
  }

  if (path.startsWith("/users/")) {
    return HELP_BY_PATH["/users/teams/members"] ?? HELP_BY_PATH["/users"];
  }

  return FALLBACK_HELP;
};

export const resolveHelpUrl = (fileName: string): string => {
  const base = import.meta.env.BASE_URL ?? "/";
  const normalizedBase = base.endsWith("/") ? base : `${base}/`;
  return `${normalizedBase}help/${fileName}`;
};
