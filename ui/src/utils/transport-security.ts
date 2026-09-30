export const isLoopbackHost = (host: string): boolean => {
  const normalized = host.replace(/^\[(.*)\]$/, "$1").toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1";
};

export const assertSecureTransport = (address: string, kind: "http" | "websocket"): void => {
  let url: URL;
  try {
    url = new URL(address);
  } catch {
    throw new Error("Enter a valid backend URL.");
  }
  const secure = kind === "http" ? "https:" : "wss:";
  const plaintext = kind === "http" ? "http:" : "ws:";
  if (url.username || url.password || (url.protocol !== secure && url.protocol !== plaintext)) {
    throw new Error("Backend URLs must use HTTP(S) or WS(S) without embedded credentials.");
  }
  if (url.protocol === plaintext && !isLoopbackHost(url.hostname)) {
    throw new Error(kind === "http" ? "Use HTTPS for a remote backend." : "Use WSS for a remote WebSocket connection.");
  }
};
