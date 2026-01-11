import { useConnectionStore } from "../stores/connection";

export interface WsMessage<T = unknown> {
  type: string;
  ts: string;
  data: T;
}

export type WsHandler = (message: WsMessage) => void;

export class WsClient {
  private socket: WebSocket | null = null;
  private readonly url: string;
  private readonly handler: WsHandler;
  private readonly onOpen?: () => void;
  private retryCount = 0;
  private readonly maxRetry = 5;

  constructor(path: string, handler: WsHandler, onOpen?: () => void) {
    const connectionStore = useConnectionStore();
    this.url = connectionStore.resolveWsUrl(path);
    this.handler = handler;
    this.onOpen = onOpen;
  }

  connect(): void {
    this.socket = new WebSocket(this.url);
    this.socket.onopen = () => {
      this.retryCount = 0;
      this.sendAuth();
      if (this.onOpen) {
        this.onOpen();
      }
    };
    this.socket.onmessage = (event) => {
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
    this.socket.onclose = () => {
      this.scheduleReconnect();
    };
  }

  send<T>(message: WsMessage<T>): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }

  close(): void {
    this.socket?.close();
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
    if (this.retryCount >= this.maxRetry) {
      return;
    }
    const delay = Math.min(1000 * 2 ** this.retryCount, 15000);
    this.retryCount += 1;
    window.setTimeout(() => {
      this.connect();
    }, delay);
  }
}
