import { describe, expect, it } from "vitest";
import { buildEventCallsignLookup, resolveEventFeedMessage } from "./event-feed";
import type { ClientEntry, TeamMemberRecord } from "../api/types";

describe("event feed callsign formatting", () => {
  const members: TeamMemberRecord[] = [
    {
      uid: "member-alpha",
      rns_identity: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      callsign: "ALPHA-1",
      client_identities: ["client-alpha"]
    },
    {
      uid: "member-bravo",
      rns_identity: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      callsign: "BRAVO-2"
    }
  ];

  it("builds callsign lookup entries from member identities and linked clients", () => {
    const lookup = buildEventCallsignLookup(members);

    expect(lookup.get("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")).toBe("ALPHA-1");
    expect(lookup.get("client-alpha")).toBe("ALPHA-1");
    expect(lookup.get("member-alpha")).toBe("ALPHA-1");
  });

  it("replaces metadata-backed destination hashes in event messages with callsigns", () => {
    const lookup = buildEventCallsignLookup(members);
    const message = resolveEventFeedMessage(
      {
        message: "Retrying message delivery to aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        metadata: {
          Destination: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        }
      },
      lookup
    );

    expect(message).toBe("Retrying message delivery to ALPHA-1");
  });

  it("derives callsigns from client announce names for delivery events", () => {
    const clients: ClientEntry[] = [
      {
        id: "fb4c70e20cfac047b899ca2f3671b50a",
        identity_id: "fb4c70e20cfac047b899ca2f3671b50a",
        display_name: "R3AKT,EMergencyMessages,Telemetry;name=Pixelcorvo",
        announce_capabilities: ["R3AKT", "EMergencyMessages", "Telemetry", "name=pixelcorvo"]
      }
    ];
    const lookup = buildEventCallsignLookup({ clients });
    const message = resolveEventFeedMessage(
      {
        message: "Retrying message delivery to fb4c70e20cfac047b899ca2f3671b50a",
        metadata: {
          Destination: "fb4c70e20cfac047b899ca2f3671b50a"
        }
      },
      lookup
    );

    expect(message).toBe("Retrying message delivery to Pixelcorvo");
  });

  it("falls back to replacing known identity tokens found directly in the message", () => {
    const lookup = buildEventCallsignLookup(members);
    const message = resolveEventFeedMessage(
      {
        message: "Message delivery failed for bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      },
      lookup
    );

    expect(message).toBe("Message delivery failed for BRAVO-2");
  });

  it("hides generated marker suffixes in marker-created event titles", () => {
    const lookup = buildEventCallsignLookup(members);
    const message = resolveEventFeedMessage(
      {
        category: "marker_created",
        message: "Marker created: neutral+07c636",
        metadata: {
          event_type: "marker.created",
          name: "neutral+07c636",
          object_type: "marker"
        }
      },
      lookup
    );

    expect(message).toBe("Marker created: neutral");
  });

  it("preserves explicit marker names without generated suffixes", () => {
    const lookup = buildEventCallsignLookup(members);
    const message = resolveEventFeedMessage(
      {
        category: "marker_created",
        message: "Marker created: Rally Point",
        metadata: {
          event_type: "marker.created",
          name: "Rally Point",
          object_type: "marker"
        }
      },
      lookup
    );

    expect(message).toBe("Marker created: Rally Point");
  });

  it("leaves unknown identities unchanged", () => {
    const lookup = buildEventCallsignLookup(members);
    const message = resolveEventFeedMessage(
      {
        message: "Message delivery failed for cccccccccccccccccccccccccccccccc",
        metadata: {
          destination: "cccccccccccccccccccccccccccccccc"
        }
      },
      lookup
    );

    expect(message).toBe("Message delivery failed for cccccccccccccccccccccccccccccccc");
  });
});
