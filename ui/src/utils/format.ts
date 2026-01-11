export const formatTimestamp = (value?: string | number | null): string => {
  if (!value) {
    return "-";
  }
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString();
};

export const formatNumber = (value?: number | null): string => {
  if (value === undefined || value === null) {
    return "-";
  }
  return new Intl.NumberFormat().format(value);
};
