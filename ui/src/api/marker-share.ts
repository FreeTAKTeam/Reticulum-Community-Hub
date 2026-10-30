import { post } from "./client";
import { endpoints } from "./endpoints";

export type MarkerShareReceipt = {
  message_id: string;
  marker_id: string;
  destination: string;
  delivery_state: string;
};

export const shareMarker = async (markerId: string, destination: string, signal?: AbortSignal): Promise<MarkerShareReceipt> => {
  const receipt = await post<Partial<MarkerShareReceipt> | null>(`${endpoints.markers}/${encodeURIComponent(markerId)}/share`,
    { destination: destination.trim() }, { retries: 0, signal });
  if (!receipt || ![receipt.message_id, receipt.marker_id, receipt.destination, receipt.delivery_state]
    .every((value) => typeof value === "string" && value.length > 0)) {
    throw new Error("The server did not return a marker delivery receipt. Check Messages before sending again.");
  }
  return receipt as MarkerShareReceipt;
};
