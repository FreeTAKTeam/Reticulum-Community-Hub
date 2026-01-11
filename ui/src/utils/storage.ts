export const loadJson = <T>(key: string, fallback: T): T => {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return fallback;
    }
    return JSON.parse(raw) as T;
  } catch (error) {
    return fallback;
  }
};

export const saveJson = (key: string, value: unknown): void => {
  window.localStorage.setItem(key, JSON.stringify(value));
};
