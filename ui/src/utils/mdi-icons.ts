const mdiIconImports = import.meta.glob("/node_modules/@mdi/svg/svg/*.svg", { as: "raw" });

const mdiIconLoaders = new Map<string, () => Promise<string>>();
Object.entries(mdiIconImports).forEach(([path, loader]) => {
  const match = path.match(/\/([^/]+)\.svg$/);
  if (match) {
    mdiIconLoaders.set(match[1], loader as () => Promise<string>);
  }
});

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
  const loader = mdiIconLoaders.get(normalized);
  if (!loader) {
    return null;
  }
  return loader();
};
