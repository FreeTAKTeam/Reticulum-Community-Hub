const nowIso = () => new Date().toISOString();

const mockState = {
  topics: [
    { TopicID: "topic-1", TopicName: "Weather", TopicPath: "environment/weather", TopicDescription: "Sensor feed" },
    { TopicID: "topic-2", TopicName: "Logistics", TopicPath: "ops/logistics", TopicDescription: "Supply status" }
  ],
  subscribers: [
    { SubscriberID: "sub-1", Destination: "deadbeef01", TopicID: "topic-1", RejectTests: 0, Metadata: {} }
  ],
  clients: [
    { identity: "deadbeef01", last_seen: nowIso(), metadata: { display_name: "Field Team Alpha" } },
    { identity: "deadbeef02", last_seen: nowIso(), metadata: { display_name: "Field Team Beta" } }
  ],
  identities: [
    {
      Identity: "deadbeef01",
      Status: "Active",
      LastSeen: nowIso(),
      Metadata: { display_name: "Field Team Alpha" },
      IsBanned: false,
      IsBlackholed: false
    },
    {
      Identity: "deadbeef02",
      Status: "Active",
      LastSeen: nowIso(),
      Metadata: { display_name: "Field Team Beta" },
      IsBanned: false,
      IsBlackholed: false
    }
  ],
  files: [{ FileID: 1, Name: "report.txt", MediaType: "text/plain", Size: 1240, CreatedAt: nowIso() }],
  images: [{ FileID: 2, Name: "snapshot.svg", MediaType: "image/svg+xml", Size: 2048, CreatedAt: nowIso() }],
  telemetry: [
    {
      id: "t-1",
      identity_id: "deadbeef01",
      display_name: "Field Team Alpha",
      topic_id: "topic-1",
      created_at: nowIso(),
      location: { lat: 37.7749, lon: -122.4194, alt: 12 },
      data: { temperature_c: 22.4 }
    }
  ],
  events: [
    {
      id: "evt-1",
      created_at: nowIso(),
      message: "Hub started",
      level: "info",
      category: "system"
    }
  ],
  configText: "[core]\napp_name=RTH Core\n"
};

let topicCounter = 3;
let subscriberCounter = 2;

const jsonResponse = (payload: unknown, status = 200) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });

const textResponse = (payload: string, status = 200, contentType = "text/plain") =>
  new Response(payload, {
    status,
    headers: { "Content-Type": contentType }
  });

const parseBody = async (body: unknown) => {
  if (body === undefined || body === null) {
    return undefined;
  }
  if (typeof body === "string") {
    try {
      return JSON.parse(body);
    } catch {
      return body;
    }
  }
  return body;
};

export const mockFetch = async (path: string, options: { method?: string; body?: unknown }) => {
  const method = (options.method ?? "GET").toUpperCase();
  const url = new URL(path, "http://localhost");
  const pathname = url.pathname;

  if (pathname === "/Status") {
    return jsonResponse({
      uptime_seconds: 4521,
      clients: mockState.clients.length,
      topics: mockState.topics.length,
      subscribers: mockState.subscribers.length,
      files: mockState.files.length,
      images: mockState.images.length,
      telemetry: {
        ingest_count: mockState.telemetry.length,
        last_ingest_at: mockState.telemetry[0]?.created_at ?? null
      }
    });
  }

  if (pathname === "/Events") {
    return jsonResponse(mockState.events);
  }

  if (pathname === "/Topic") {
    if (method === "GET") {
      return jsonResponse(mockState.topics);
    }
    if (method === "POST") {
      const body = (await parseBody(options.body)) as any;
      const topic = {
        TopicID: body?.TopicID ?? `topic-${topicCounter++}`,
        TopicName: body?.TopicName ?? "New Topic",
        TopicPath: body?.TopicPath ?? `custom/${topicCounter}`,
        TopicDescription: body?.TopicDescription ?? ""
      };
      mockState.topics.push(topic);
      return jsonResponse(topic);
    }
    if (method === "PATCH") {
      const body = (await parseBody(options.body)) as any;
      const target = mockState.topics.find((item) => item.TopicID === body?.TopicID);
      if (!target) {
        return jsonResponse({ detail: "Topic not found" }, 404);
      }
      Object.assign(target, body ?? {});
      return jsonResponse(target);
    }
    if (method === "DELETE") {
      const id = url.searchParams.get("id");
      mockState.topics = mockState.topics.filter((topic) => topic.TopicID !== id);
      return jsonResponse({ deleted: true });
    }
  }

  if (pathname === "/Subscriber") {
    if (method === "GET") {
      return jsonResponse(mockState.subscribers);
    }
    if (method === "PATCH") {
      const body = (await parseBody(options.body)) as any;
      const target = mockState.subscribers.find((item) => item.SubscriberID === body?.SubscriberID);
      if (!target) {
        return jsonResponse({ detail: "Subscriber not found" }, 404);
      }
      Object.assign(target, body ?? {});
      return jsonResponse(target);
    }
    if (method === "DELETE") {
      const id = url.searchParams.get("id");
      mockState.subscribers = mockState.subscribers.filter((sub) => sub.SubscriberID !== id);
      return jsonResponse({ deleted: true });
    }
  }

  if (pathname === "/Subscriber/Add" && method === "POST") {
    const body = (await parseBody(options.body)) as any;
    const subscriber = {
      SubscriberID: body?.SubscriberID ?? `sub-${subscriberCounter++}`,
      Destination: body?.Destination ?? "deadbeef01",
      TopicID: body?.TopicID ?? "topic-1",
      RejectTests: body?.RejectTests ?? 0,
      Metadata: body?.Metadata ?? {}
    };
    mockState.subscribers.push(subscriber);
    return jsonResponse(subscriber);
  }

  if (pathname === "/File") {
    return jsonResponse(mockState.files);
  }

  if (pathname === "/Image") {
    return jsonResponse(mockState.images);
  }

  const fileRawMatch = pathname.match(/^\/File\/(\d+)\/raw$/);
  if (fileRawMatch) {
    const content = "Mock file content from RTH.";
    return textResponse(content, 200, "text/plain");
  }

  const imageRawMatch = pathname.match(/^\/Image\/(\d+)\/raw$/);
  if (imageRawMatch) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#0b1120"/><text x="20" y="90" fill="#38bdf8" font-size="20">Mock Image</text></svg>`;
    return textResponse(svg, 200, "image/svg+xml");
  }

  if (pathname === "/Config") {
    if (method === "GET") {
      return textResponse(mockState.configText);
    }
    if (method === "PUT") {
      const body = await parseBody(options.body);
      mockState.configText = typeof body === "string" ? body : mockState.configText;
      return jsonResponse({ applied: true });
    }
  }

  if (pathname === "/Config/Validate" && method === "POST") {
    return jsonResponse({ valid: true });
  }

  if (pathname === "/Config/Rollback" && method === "POST") {
    return jsonResponse({ rolled_back: true });
  }

  if (pathname === "/Help") {
    return textResponse("# Commands\n\n- Help\n- Examples\n");
  }

  if (pathname === "/Examples") {
    return textResponse("# Examples\n\n{ \"Command\": \"ListTopic\" }\n");
  }

  if (pathname === "/Command/DumpRouting") {
    return jsonResponse({ routes: ["deadbeef01", "deadbeef02"] });
  }

  if (pathname === "/Client") {
    return jsonResponse(mockState.clients);
  }

  const clientActionMatch = pathname.match(/^\/Client\/(.+?)\/(Ban|Unban|Blackhole)$/);
  if (clientActionMatch && method === "POST") {
    const identity = clientActionMatch[1];
    const action = clientActionMatch[2];
    const target = mockState.identities.find((entry) => entry.Identity === identity);
    if (!target) {
      return jsonResponse({ detail: "Identity not found" }, 404);
    }
    if (action === "Ban") {
      target.IsBanned = true;
    }
    if (action === "Unban") {
      target.IsBanned = false;
      target.IsBlackholed = false;
    }
    if (action === "Blackhole") {
      target.IsBlackholed = true;
    }
    return jsonResponse(target);
  }

  if (pathname === "/Identities") {
    return jsonResponse(mockState.identities);
  }

  if (pathname === "/Telemetry") {
    return jsonResponse({ entries: mockState.telemetry });
  }

  if (pathname === "/api/v1/app/info") {
    return jsonResponse({
      name: "RTH Core",
      version: "0.1.0",
      description: "Mock hub",
      rns_version: "0.9.0",
      lxmf_version: "0.7.0",
      storage_paths: {
        storage: "C:/rth/storage",
        files: "C:/rth/storage/files",
        images: "C:/rth/storage/images"
      }
    });
  }

  return jsonResponse({ detail: "Mock route not found" }, 404);
};

export const mockTelemetryEntry = () => ({
  id: `t-${Math.floor(Math.random() * 10000)}`,
  identity_id: "deadbeef01",
  display_name: "Field Team Alpha",
  topic_id: "topic-1",
  created_at: nowIso(),
  location: {
    lat: 37.7749 + Math.random() * 0.01,
    lon: -122.4194 + Math.random() * 0.01,
    alt: 10 + Math.random() * 5
  },
  data: { temperature_c: 22 + Math.random() * 2 }
});

export const mockSystemEvent = () => ({
  id: `evt-${Math.floor(Math.random() * 10000)}`,
  created_at: nowIso(),
  message: "Heartbeat received",
  level: "info",
  category: "system"
});

export const mockStatusPayload = () => ({
  uptime_seconds: 4521 + Math.floor(Math.random() * 100),
  clients: mockState.clients.length,
  topics: mockState.topics.length,
  subscribers: mockState.subscribers.length,
  files: mockState.files.length,
  images: mockState.images.length,
  telemetry: {
    ingest_count: mockState.telemetry.length,
    last_ingest_at: mockState.telemetry[0]?.created_at ?? null
  }
});
