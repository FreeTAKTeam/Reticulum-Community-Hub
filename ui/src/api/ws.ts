import { mockStatusPayload, mockSystemEvent, mockTelemetryEntry } from "./mock";
import { useConnectionStore } from "../stores/connection";

export interface WsMessage<T = unknown> {
  type: string;
  ts: string;
  data: T;
}

export type WsHandler = (message: WsMessage) => void;

export class WsClient {
  private socket: WebSocket | null = null;
  private readonly path: string;
  private readonly url: string;
  private readonly handler: WsHandler;
  private readonly onOpen?: () => void;
  private retryCount = 0;
  private readonly maxRetry = 5;
  private registered = false;
  private shouldReconnect = true;
  private mockInterval: number | undefined;
  private reconnectTimer: number | undefined;
  private readonly useMock = import.meta.env.VITE_RTH_MOCK === "true";

  constructor(path: string, handler: WsHandler, onOpen?: () => void) {
    const connectionStore = useConnectionStore();
    this.path = path;
    this.url = connectionStore.resolveWsUrl(path);
    this.handler = handler;
    this.onOpen = onOpen;
  }

  connect(): void {
    if (this.useMock) {
      this.connectMock();
      return;
    }
    if (this.socket && (this.socket.readyState === WebSocket.CONNECTING || this.socket.readyState === WebSocket.OPEN)) {
      return;
    }
    this.clearReconnectTimer();
    this.shouldReconnect = true;
    const socket = new WebSocket(this.url);
    this.socket = socket;
    socket.onopen = () => {
      if (this.socket !== socket) {
        return;
      }
      this.retryCount = 0;
      this.sendAuth();
      this.registerConnection();
      if (this.onOpen) {
        this.onOpen();
      }
    };
    socket.onmessage = (event) => {
      if (this.socket !== socket) {
        return;
      }
      try {
        const payload = JSON.parse(event.data) as WsMessage;
        if (payload.type === "ping") {
          this.send({ type: "pong", ts: new Date().toISOString(), data: payload.data });
        } else {
          this.handler(payload);
        }
      } catch (error) {
        console.error("Invalid WS payload", error);
      }
    };
    socket.onerror = () => {
      if (this.socket !== socket) {
        return;
      }
      socket.close();
    };
    socket.onclose = () => {
      const isActiveSocket = this.socket === socket;
      if (isActiveSocket) {
        this.socket = null;
      }
      this.unregisterConnection();
      if (isActiveSocket && this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };
  }

  send<T>(message: WsMessage<T>): void {
    if (this.useMock) {
      return;
    }
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }

  close(): void {
    this.shouldReconnect = false;
    this.clearReconnectTimer();
    if (this.mockInterval) {
      window.clearInterval(this.mockInterval);
      this.mockInterval = undefined;
    }
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    this.unregisterConnection();
  }

  private sendAuth(): void {
    const connectionStore = useConnectionStore();
    this.send({
      type: "auth",
      ts: new Date().toISOString(),
      data: {
        token: connectionStore.token || undefined,
        api_key: connectionStore.apiKey || undefined
      }
    });
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect || this.retryCount >= this.maxRetry || this.reconnectTimer !== undefined) {
      return;
    }
    const delay = Math.min(1000 * 2 ** this.retryCount, 15000);
    this.retryCount += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = undefined;
      if (!this.shouldReconnect) {
        return;
      }
      this.connect();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer === undefined) {
      return;
    }
    window.clearTimeout(this.reconnectTimer);
    this.reconnectTimer = undefined;
  }

  private registerConnection(): void {
    if (this.registered) {
      return;
    }
    const connectionStore = useConnectionStore();
    connectionStore.registerWsConnection();
    this.registered = true;
  }

  private unregisterConnection(): void {
    if (!this.registered) {
      return;
    }
    const connectionStore = useConnectionStore();
    connectionStore.unregisterWsConnection();
    this.registered = false;
  }

  private connectMock(): void {
    this.registerConnection();
    window.setTimeout(() => {
      if (this.onOpen) {
        this.onOpen();
      }
      if (this.path.includes("/events/system")) {
        this.handler({ type: "system.status", ts: new Date().toISOString(), data: mockStatusPayload() });
        this.handler({ type: "system.event", ts: new Date().toISOString(), data: mockSystemEvent() });
        this.mockInterval = window.setInterval(() => {
          this.handler({ type: "system.status", ts: new Date().toISOString(), data: mockStatusPayload() });
          this.handler({ type: "system.event", ts: new Date().toISOString(), data: mockSystemEvent() });
        }, 8000);
      }
      if (this.path.includes("/telemetry/stream")) {
        this.handler({
          type: "telemetry.snapshot",
          ts: new Date().toISOString(),
          data: { entries: [mockTelemetryEntry()] }
        });
        this.mockInterval = window.setInterval(() => {
          this.handler({
            type: "telemetry.update",
            ts: new Date().toISOString(),
            data: { entry: mockTelemetryEntry() }
          });
        }, 6000);
      }
      if (this.path.includes("/messages/stream")) {
        this.handler({
          type: "message.receive",
          ts: new Date().toISOString(),
          data: {
            entry: {
              MessageID: `mock-${Date.now()}`,
              Direction: "inbound",
              Scope: "dm",
              State: "delivered",
              Content: "Mocked inbound chat message.",
              Source: "deadbeef01",
              Destination: null,
              TopicID: null,
              Attachments: [],
              CreatedAt: new Date().toISOString(),
              UpdatedAt: new Date().toISOString()
            }
          }
        });
        this.mockInterval = window.setInterval(() => {
          this.handler({
            type: "message.receive",
            ts: new Date().toISOString(),
            data: {
              entry: {
                MessageID: `mock-${Date.now()}`,
                Direction: "inbound",
                Scope: "broadcast",
                State: "delivered",
                Content: "Mock broadcast update from the hub.",
                Source: "deadbeef02",
                Destination: null,
                TopicID: null,
                Attachments: [],
                CreatedAt: new Date().toISOString(),
                UpdatedAt: new Date().toISOString()
              }
            }
          });
        }, 7000);
      }
    }, 150);
  }
}
