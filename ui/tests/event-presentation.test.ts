import { describe, expect, it } from "vitest";
import type { EventEntry } from "../src/api/types";
import { eventCategory, presentEvent } from "../src/utils/event-presentation";

const RESCUE = "0f1e2d3c4b5a69788796a5b4c3d2e1f0";
const ALPHA = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
const lookups = {
  identities: new Map([[RESCUE, "Rescue Mobile"], [ALPHA, "Alpha Sideband"]]),
  missions: new Map([["mission-1", "SAR – Spruce Ridge"]])
};
const event = (category: string, message: string, metadata: Record<string, unknown> = {}, level = "info"): EventEntry =>
  ({ id: "e", category, message, metadata, level, created_at: "2026-11-19T09:45:56Z" });

describe("event presentation", () => {
  it("hides broker bookkeeping as transport and names the peer", () => {
    const inbound = presentEvent(event("durable_broker_handled", "inbound", { position: 7, source: RESCUE }), lookups);
    expect(inbound).toMatchObject({ category: "transport", transport: true, title: "Inbound LXMF message processed", summary: "from Rescue Mobile" });
    const receipt = presentEvent(event("durable_broker_handled", "receipt", { status: "delivered", destination: ALPHA }), lookups);
    expect(receipt.title).toBe("Delivery receipt processed");
    expect(receipt.summary).toBe("for Alpha Sideband · Delivered");
  });

  it("turns unsupported commands into an error naming the sender", () => {
    const presented = presentEvent(
      event("lxmf_command_diagnostic", "unsupported LXMF FIELD_COMMANDS (0x09)", { source: RESCUE, message_id: "m1" }),
      lookups
    );
    expect(presented.category).toBe("errors");
    expect(presented.title).toBe("Unsupported command from Rescue Mobile");
    expect(presented.summary).toBe("unsupported LXMF FIELD_COMMANDS (0x09)");
  });

  it("says who a telemetry snapshot or a message went to", () => {
    expect(presentEvent(event("telemetry_request", "Telemetry collector snapshot served", { entry_count: 6, unavailable_records: 0, peer: ALPHA }), lookups))
      .toMatchObject({ category: "location", title: "Telemetry snapshot sent to Alpha Sideband", summary: "6 entries" });
    expect(presentEvent(event("message_sent", "Message sent from hub", { destination: ALPHA, delivery_method: "direct", delivery_state: "sent" }), lookups))
      .toMatchObject({ category: "messages", title: "Message sent to Alpha Sideband", summary: "Direct · Sent" });
    expect(presentEvent(event("message_failed", "Message failed", { topic_id: "ops", drop_reason: "no_recipients" }), lookups))
      .toMatchObject({ category: "errors", title: "Message to topic ops failed", summary: "No recipients" });
  });

  it("labels broadcasts and hides internal marker telemetry copies", () => {
    expect(presentEvent(event("message_sent", "Message sent from hub", { delivery_method: "durable_broker", delivery_state: "failed" }), lookups))
      .toMatchObject({ title: "Broadcast message sent", summary: "Failed" });
    expect(presentEvent(event("message_failed", "Message failed", { drop_reason: "no_recipients" }), lookups).title).toBe("Broadcast message failed");
    expect(presentEvent(event("marker_telemetry_recorded", "Marker telemetry recorded"), lookups)).toMatchObject({ category: "transport", transport: true });
  });

  it("names the mission for registry link events", () => {
    expect(presentEvent(event("mission.registry.mission.marker.linked", "Mission marker link notification", { mission_uid: "mission-1", marker_id: "x", recipient_fanout: 3 }), lookups))
      .toMatchObject({ category: "missions", title: "Marker linked to mission SAR – Spruce Ridge", summary: "3 recipients notified" });
  });

  it("keeps readable server messages, resolving identities to names", () => {
    expect(presentEvent(event("message_received", `Message received from ${RESCUE}`, { source: RESCUE, topic: "search" }), lookups))
      .toMatchObject({ title: "Message received from Rescue Mobile", summary: "topic search" });
    expect(presentEvent(event("mission.joined", "mission.joined"), lookups).title).toBe("Mission joined");
  });

  it("lists details with names beside short addresses", () => {
    const { details } = presentEvent(event("message_sent", "Message sent from hub", { destination: ALPHA, message_id: "7c3e91a0f4b2c9d8e7f6a5b4e18d", delivery_state: "sent" }), lookups);
    expect(details).toEqual([
      { label: "Destination", value: "Alpha Sideband ", mono: "a1b2c3d4…6d7e8f90" },
      { label: "Message id", value: "", mono: "7c3e91a0…a5b4e18d" },
      { label: "Delivery state", value: "sent" }
    ]);
  });

  it("files events by level and type", () => {
    expect(eventCategory(event("startup", "Hub started"))).toBe("system");
    expect(eventCategory(event("marker_created", "Marker created: A"))).toBe("map");
    expect(eventCategory(event("startup", "boom", {}, "error"))).toBe("errors");
    expect(eventCategory(event("IdentityAnnounceRecorded", "Identity announce recorded"))).toBe("users");
  });
});
