import { get } from "./client";

const PAGE_SIZE = 100;
const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

/** A legacy Python array is complete; Rust pages must explicitly describe continuation. */
export const loadDirectory = async (
  path: string,
  identityField: string,
  assertCurrent: () => void,
  publish: (items: Record<string, unknown>[], total: number, first: boolean) => void
) => {
  for (let page = 1; ; page += 1) {
    const response = await get<unknown>(`${path}?page=${page}&per_page=${PAGE_SIZE}`);
    assertCurrent();
    const legacy = Array.isArray(response);
    if (legacy && page !== 1) { throw new Error(`Invalid ${path} pagination response.`); }
    const envelope = isRecord(response) ? response : null;
    const items: unknown = legacy ? response : envelope?.items;
    if (!Array.isArray(items) || !items.every((item) => isRecord(item) && typeof item[identityField] === "string")) {
      throw new Error(`Invalid ${path} directory response.`);
    }
    const total = legacy ? items.length : envelope?.total;
    if (typeof total !== "number" || !Number.isSafeInteger(total) || total < 0) {
      throw new Error(`Invalid ${path} directory total.`);
    }
    if (!legacy && (!envelope || envelope.page !== page || envelope.per_page !== PAGE_SIZE ||
      items.length > PAGE_SIZE || typeof envelope.has_next !== "boolean" ||
      envelope.total_pages !== Math.ceil(total / PAGE_SIZE) ||
      envelope.has_next !== (page < Math.ceil(total / PAGE_SIZE)) ||
      items.length !== Math.min(PAGE_SIZE, Math.max(0, total - (page - 1) * PAGE_SIZE)))) {
      throw new Error(`Invalid ${path} pagination response.`);
    }
    publish(items, total, page === 1);
    if (legacy || !envelope?.has_next) { return; }
  }
};
