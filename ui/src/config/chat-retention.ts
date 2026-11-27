import defaults from "./chat-retention.json";

export type ChatRetentionConfig = typeof defaults;

/** Presentation policy lives in configuration, not in cache or component code. */
export const resolveChatRetention = (env: Record<string, unknown> = import.meta.env): ChatRetentionConfig => {
  const result = { ...defaults };
  for (const key of Object.keys(defaults) as (keyof ChatRetentionConfig)[]) {
    const name = `VITE_CHAT_${key.replace(/[A-Z]/g, (letter) => `_${letter}`).toUpperCase()}`;
    const value = env[name];
    if (value === undefined || value === "") { continue; }
    const parsed = Number(value);
    if (!Number.isSafeInteger(parsed) || parsed < 1) { throw new Error(`${name} must be a positive integer.`); }
    result[key] = parsed;
  }
  if (result.conversationMessages > result.globalMessages || result.pageSize > result.conversationMessages) {
    throw new Error("Chat page size must fit the conversation limit, which must fit the global message limit.");
  }
  if (result.maintenanceMs > result.idleMs) { throw new Error("Chat maintenance interval must not exceed inactivity limit."); }
  return Object.freeze(result);
};
