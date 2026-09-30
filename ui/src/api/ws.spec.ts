// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { WsClient } from "./ws";
import { useConnectionStore } from "../stores/connection";

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readonly url: string;
  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(payload: string): void {
    this.sent.push(payload);
  }

  close(): void {
    this.emitClose();
  }

  emitOpen(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  emitClose(): void {
    if (this.readyState === FakeWebSocket.CLOSED) {
      return;
    }
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close"));
  }
}

describe("WsClient reconnect lifecycle", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setActivePinia(createPinia());
    FakeWebSocket.instances = [];
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("does not open duplicate sockets while one is already active", () => {
    const client = new WsClient("/events/system", vi.fn());

    client.connect();
    client.connect();

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("cancels a pending reconnect when the client is explicitly closed", () => {
    const client = new WsClient("/events/system", vi.fn());

    client.connect();
    expect(FakeWebSocket.instances).toHaveLength(1);

    FakeWebSocket.instances[0].emitClose();
    client.close();
    vi.advanceTimersByTime(2000);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("rejects a remote plaintext socket before sending credentials", () => {
    const connection = useConnectionStore();
    connection.baseUrl = "https://remote.example";
    connection.wsBaseUrl = "ws://remote.example";
    connection.apiKey = "fixture-key";
    connection.authMode = "apiKey";
    new WsClient("/events/system", vi.fn()).connect();
    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(connection.authMessage).toMatch(/WSS/);
  });

  it("does not send credentials to an old target after connection settings change", () => {
    const connection = useConnectionStore();
    connection.baseUrl = "https://first.example";
    const client = new WsClient("/events/system", vi.fn());
    client.connect();
    const socket = FakeWebSocket.instances[0];
    connection.baseUrl = "https://second.example";
    connection.apiKey = "new-target-key";
    connection.authMode = "apiKey";
    socket.emitOpen();
    expect(socket.sent).toHaveLength(0);
    expect(socket.readyState).toBe(FakeWebSocket.CLOSED);
    client.close();
  });

  it("rejects traffic on an already open socket when the target changes", () => {
    const connection = useConnectionStore();
    connection.baseUrl = "https://first.example";
    const handler = vi.fn();
    const client = new WsClient("/events/system", handler);
    client.connect();
    const socket = FakeWebSocket.instances[0];
    socket.emitOpen();
    expect(socket.sent).toHaveLength(1);
    connection.baseUrl = "https://second.example";
    socket.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "message.receive", data: "old target" }) }));
    client.send({ type: "command", ts: "fixture", data: "new target work" });
    expect(socket.sent).toHaveLength(1);
    expect(handler).not.toHaveBeenCalled();
    expect(socket.readyState).toBe(FakeWebSocket.CLOSED);
  });
});
