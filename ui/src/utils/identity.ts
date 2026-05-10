export const shortHash = (value?: string, head = 4, tail = 4): string => {
  if (!value) {
    return "unknown";
  }
  if (value.length <= head + tail + 1) {
    return value;
  }
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
};

export const resolveIdentityLabel = (displayName?: string, identity?: string): string => {
  if (displayName) {
    return displayName;
  }
  if (identity) {
    return shortHash(identity);
  }
  return "unknown";
};
