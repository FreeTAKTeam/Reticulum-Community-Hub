type WrappedList<T> = {
  value?: T[];
  Value?: T[];
  items?: T[];
  Items?: T[];
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

export const unwrapApiList = <T>(payload: unknown): T[] => {
  if (Array.isArray(payload)) {
    return payload as T[];
  }
  if (!isRecord(payload)) {
    return [];
  }

  const wrapped = payload as WrappedList<T>;
  if (Array.isArray(wrapped.value)) {
    return wrapped.value;
  }
  if (Array.isArray(wrapped.Value)) {
    return wrapped.Value;
  }
  if (Array.isArray(wrapped.items)) {
    return wrapped.items;
  }
  if (Array.isArray(wrapped.Items)) {
    return wrapped.Items;
  }
  return [];
};
