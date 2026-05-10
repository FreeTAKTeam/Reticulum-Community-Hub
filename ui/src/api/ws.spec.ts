// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { WsClient } from "./ws";

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
});
