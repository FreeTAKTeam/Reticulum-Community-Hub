import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { WsClient } from "../src/api/ws";

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static CONNECTING = 0;
  static instances: MockWebSocket[] = [];
  readyState = MockWebSocket.CONNECTING;
  sent: string[] = [];
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onclose?: () => void;

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  receive(data: string) {
    this.onmessage?.({ data });
  }
}

describe("ws client", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    MockWebSocket.instances = [];
    globalThis.WebSocket = MockWebSocket as any;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("sends auth and pong", () => {
    const handler = vi.fn();
    const client = new WsClient("/events/system", handler);
    client.connect();

    const socket = MockWebSocket.instances[0];
    socket.open();
    expect(socket.sent[0]).toContain("\"type\":\"auth\"");

    socket.receive(JSON.stringify({ type: "ping", ts: new Date().toISOString(), data: {} }));
    expect(socket.sent.some((message) => message.includes("\"type\":\"pong\""))).toBe(true);
  });

  it("reconnects after close", async () => {
    vi.useFakeTimers();
    const handler = vi.fn();
    const client = new WsClient("/events/system", handler);
    client.connect();

    const socket = MockWebSocket.instances[0];
    socket.open();
    socket.close();

    await vi.runAllTimersAsync();
    expect(MockWebSocket.instances.length).toBeGreaterThan(1);
  });
});
