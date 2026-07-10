import { describe, expect, it } from "vitest";
import {
  DEFAULT_TCP_COMMUNITY_ENDPOINT,
  TCP_COMMUNITY_SERVERS,
  endpointHostPort,
  normalizeTcpEndpoint
} from "../src/utils/tcp-community-servers";

describe("tcp community servers", () => {
  it("defaults to the REM R3AKT community server", () => {
    expect(TCP_COMMUNITY_SERVERS[0].name).toBe("R3AKT Server");
    expect(DEFAULT_TCP_COMMUNITY_ENDPOINT).toBe("134.122.46.48:37428");
  });

  it("keeps rmap available as a selectable REM community server", () => {
    expect(
      TCP_COMMUNITY_SERVERS.some(
        (server) => server.name === "rmap" && server.host === "rmap.world" && server.port === 4242
      )
    ).toBe(true);
  });

  it("normalizes custom TCP endpoint input", () => {
    expect(normalizeTcpEndpoint("tcp://mesh.example.org:5151")).toBe("mesh.example.org:5151");
    expect(endpointHostPort("mesh.example.org:5151")).toEqual({
      host: "mesh.example.org",
      port: "5151"
    });
    expect(normalizeTcpEndpoint("mesh.example.org")).toBe("");
  });
});
