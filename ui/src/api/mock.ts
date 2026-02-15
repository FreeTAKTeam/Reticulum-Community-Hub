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
  chatMessages: [
    {
      MessageID: "msg-1",
      Direction: "inbound",
      Scope: "dm",
      State: "delivered",
      Content: "Signal check from the field.",
      Source: "deadbeef01",
      Destination: null,
      TopicID: null,
      Attachments: [],
      CreatedAt: nowIso(),
      UpdatedAt: nowIso()
    }
  ],
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
  markers: [
    {
      object_destination_hash: "marker-obj-1",
      origin_rch: "origin-1",
      type: "fire",
      symbol: "fire",
      name: "fire+demo",
      category: "napsg",
      position: { lat: 37.777, lon: -122.42 },
      time: nowIso(),
      stale_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
      created_at: nowIso(),
      updated_at: nowIso(),
      notes: "Initial mock marker"
    }
  ],
  zones: [
    {
      zone_id: "zone-1",
      name: "Ops Corridor",
      points: [
        { lat: 37.78, lon: -122.45 },
        { lat: 37.81, lon: -122.43 },
        { lat: 37.79, lon: -122.4 }
      ],
      created_at: nowIso(),
      updated_at: nowIso()
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
  configText: "[core]\napp_name=RCH UI\n",
  reticulumConfigText:
    "[reticulum]\n" +
    "enable_transport = yes\n" +
    "share_instance = yes\n" +
    "\n" +
    "[logging]\n" +
    "loglevel = 4\n" +
    "\n" +
    "[interfaces]\n" +
    "[[UDP test]]\n" +
    "type = UDPInterface\n" +
    "interface_enabled = true\n" +
    "listen_ip = 0.0.0.0\n" +
    "listen_port = 4242\n" +
    "forward_ip = 255.255.255.255\n" +
    "forward_port = 4242\n",
  reticulumCapabilities: {
    runtime_active: true,
    os: "windows",
    identity_hash_hex_length: 20,
    supported_interface_types: [
      "AutoInterface",
      "TCPClientInterface",
      "TCPServerInterface",
      "UDPInterface",
      "I2PInterface",
      "SerialInterface",
      "KISSInterface",
      "AX25KISSInterface",
      "PipeInterface",
      "RNodeInterface",
      "RNodeMultiInterface"
    ],
    unsupported_interface_types: ["BackboneInterface", "RNodeIPInterface"],
    discoverable_interface_types: ["AutoInterface", "BackboneInterface", "TCPServerInterface", "UDPInterface"],
    autoconnect_interface_types: ["TCPClientInterface", "UDPInterface"],
    rns_version: "1.1.3"
  },
  reticulumDiscovery: {
    runtime_active: true,
    should_autoconnect: true,
    max_autoconnected_interfaces: 3,
    required_discovery_value: 14,
    interface_discovery_sources: [],
    refreshed_at: nowIso(),
    discovered_interfaces: [
      {
        discovery_hash: "d1c0very1",
        status: "available",
        status_code: 1,
        type: "TCPClientInterface",
        name: "Northern Relay",
        transport: "tcp",
        transport_id: "north-relay",
        network_id: "field-net",
        hops: 2,
        value: 15,
        received: nowIso(),
        last_heard: nowIso(),
        heard_count: 4,
        reachable_on: "10.1.40.8",
        port: 4242,
        config_entry: {
          name: "Northern Relay",
          type: "TCPClientInterface",
          interface_enabled: "yes",
          target_host: "10.1.40.8",
          target_port: "4242"
        }
      }
    ]
  }
};

const mockMarkerSymbols = [
  { id: "marker", set: "mdi", mdi: "map-marker", description: "Marker", category: "general" },
  { id: "vehicle", set: "mdi", mdi: "car", description: "Vehicle", category: "mobility" },
  { id: "drone", set: "mdi", mdi: "drone", description: "Drone", category: "mobility" },
  { id: "animal", set: "mdi", mdi: "paw", description: "Animal", category: "wildlife" },
  { id: "sensor", set: "mdi", mdi: "radar", description: "Sensor", category: "equipment" },
  { id: "radio", set: "mdi", mdi: "radio", description: "Radio", category: "equipment" },
  { id: "antenna", set: "mdi", mdi: "antenna", description: "Antenna", category: "equipment" },
  { id: "camera", set: "mdi", mdi: "camera", description: "Camera", category: "equipment" },
  { id: "fire", set: "mdi", mdi: "fire", description: "Fire", category: "incident" },
  { id: "flood", set: "mdi", mdi: "home-flood", description: "Flood", category: "incident" },
  { id: "person", set: "mdi", mdi: "account", description: "Person", category: "people" },
  { id: "group", set: "mdi", mdi: "account-group", description: "Group / Community", category: "people" },
  { id: "infrastructure", set: "mdi", mdi: "office-building", description: "Infrastructure", category: "infrastructure" },
  { id: "medic", set: "mdi", mdi: "hospital", description: "Medic", category: "medical" },
  { id: "alert", set: "mdi", mdi: "alert", description: "Alert", category: "incident" },
  { id: "task", set: "mdi", mdi: "clipboard-check", description: "Task", category: "task" }
];

let topicCounter = 3;
let subscriberCounter = 2;
let chatMessageCounter = 2;
let attachmentCounter = 3;
let markerCounter = 2;
let zoneCounter = 2;

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

  if (pathname === "/Control/Status") {
    return jsonResponse({
      status: "running",
      pid: 4321,
      host: "127.0.0.1",
      port: 8000,
      uptime_seconds: 4521
    });
  }

  if (pathname === "/Control/Start" && method === "POST") {
    return jsonResponse({
      status: "running",
      pid: 4321,
      host: "127.0.0.1",
      port: 8000,
      uptime_seconds: 1
    });
  }

  if (pathname === "/Control/Stop" && method === "POST") {
    return jsonResponse({ status: "stopping" });
  }

  if (pathname === "/Control/Announce" && method === "POST") {
    return jsonResponse({ status: "announce sent" });
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

  const fileDetailMatch = pathname.match(/^\/File\/(\d+)$/);
  if (fileDetailMatch) {
    const id = Number(fileDetailMatch[1]);
    const target = mockState.files.find((entry) => entry.FileID === id);
    if (!target) {
      return jsonResponse({ detail: "File not found" }, 404);
    }
    if (method === "DELETE") {
      mockState.files = mockState.files.filter((entry) => entry.FileID !== id);
    }
    return jsonResponse(target);
  }

  if (pathname === "/Image") {
    return jsonResponse(mockState.images);
  }

  const imageDetailMatch = pathname.match(/^\/Image\/(\d+)$/);
  if (imageDetailMatch) {
    const id = Number(imageDetailMatch[1]);
    const target = mockState.images.find((entry) => entry.FileID === id);
    if (!target) {
      return jsonResponse({ detail: "Image not found" }, 404);
    }
    if (method === "DELETE") {
      mockState.images = mockState.images.filter((entry) => entry.FileID !== id);
    }
    return jsonResponse(target);
  }

  if (pathname === "/Chat/Messages") {
    return jsonResponse(mockState.chatMessages);
  }

  if (pathname === "/Chat/Message" && method === "POST") {
    const body = (await parseBody(options.body)) as any;
    const message = {
      MessageID: `msg-${chatMessageCounter++}`,
      Direction: "outbound",
      Scope: body?.Scope ?? "broadcast",
      State: "sent",
      Content: body?.Content ?? "",
      Source: "hub",
      Destination: body?.Destination ?? null,
      TopicID: body?.TopicID ?? null,
      Attachments: [],
      CreatedAt: nowIso(),
      UpdatedAt: nowIso()
    };
    mockState.chatMessages.push(message);
    return jsonResponse(message);
  }

  if (pathname === "/Chat/Attachment" && method === "POST") {
    const attachment = {
      FileID: attachmentCounter++,
      Name: "mock-upload.bin",
      MediaType: "application/octet-stream",
      Size: 2048,
      Category: "file"
    };
    return jsonResponse(attachment);
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

  if (pathname === "/Reticulum/Config") {
    if (method === "GET") {
      return textResponse(mockState.reticulumConfigText);
    }
    if (method === "PUT") {
      const body = await parseBody(options.body);
      mockState.reticulumConfigText = typeof body === "string" ? body : mockState.reticulumConfigText;
      return jsonResponse({ applied: true });
    }
  }

  if (pathname === "/Reticulum/Interfaces/Capabilities") {
    return jsonResponse(mockState.reticulumCapabilities);
  }

  if (pathname === "/Reticulum/Discovery") {
    return jsonResponse({
      ...mockState.reticulumDiscovery,
      refreshed_at: nowIso()
    });
  }

  if (pathname === "/Config/Validate" && method === "POST") {
    return jsonResponse({ valid: true });
  }

  if (pathname === "/Config/Rollback" && method === "POST") {
    return jsonResponse({ rolled_back: true });
  }

  if (pathname === "/Reticulum/Config/Validate" && method === "POST") {
    return jsonResponse({ valid: true });
  }

  if (pathname === "/Reticulum/Config/Rollback" && method === "POST") {
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

  if (pathname === "/api/markers") {
    if (method === "GET") {
      return jsonResponse(mockState.markers);
    }
    if (method === "POST") {
      const body = (await parseBody(options.body)) as any;
      const objectHash = `marker-obj-${markerCounter++}`;
      const now = nowIso();
      const marker = {
        object_destination_hash: objectHash,
        origin_rch: "origin-1",
        type: body?.type ?? body?.symbol ?? "marker",
        symbol: body?.symbol ?? body?.type ?? "marker",
        name: body?.name ?? `marker-${markerCounter}`,
        category: body?.category ?? body?.symbol ?? "marker",
        position: { lat: body?.lat ?? 0, lon: body?.lon ?? 0 },
        time: now,
        stale_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
        created_at: now,
        updated_at: now,
        notes: body?.notes ?? null
      };
      mockState.markers.push(marker);
      return jsonResponse(
        { object_destination_hash: marker.object_destination_hash, created_at: marker.created_at },
        201
      );
    }
  }

  if (pathname === "/api/zones") {
    if (method === "GET") {
      return jsonResponse(mockState.zones);
    }
    if (method === "POST") {
      const body = (await parseBody(options.body)) as any;
      const now = nowIso();
      const zone = {
        zone_id: `zone-${zoneCounter++}`,
        name: typeof body?.name === "string" ? body.name.trim() : "",
        points: Array.isArray(body?.points) ? body.points : [],
        created_at: now,
        updated_at: now
      };
      if (!zone.name) {
        return jsonResponse({ detail: "Zone name is required" }, 400);
      }
      if (zone.points.length < 3) {
        return jsonResponse({ detail: "Zone must contain at least 3 points" }, 400);
      }
      mockState.zones.push(zone);
      return jsonResponse({ zone_id: zone.zone_id, created_at: zone.created_at }, 201);
    }
  }

  const zoneMatch = pathname.match(/^\/api\/zones\/(.+?)$/);
  if (zoneMatch && method === "PATCH") {
    const zoneId = zoneMatch[1];
    const body = (await parseBody(options.body)) as any;
    const target = mockState.zones.find((entry) => entry.zone_id === zoneId);
    if (!target) {
      return jsonResponse({ detail: "Zone not found" }, 404);
    }
    if (typeof body?.name === "string") {
      const nextName = body.name.trim();
      if (!nextName) {
        return jsonResponse({ detail: "Zone name is required" }, 400);
      }
      target.name = nextName;
    }
    if (Array.isArray(body?.points)) {
      if (body.points.length < 3) {
        return jsonResponse({ detail: "Zone must contain at least 3 points" }, 400);
      }
      target.points = body.points;
    }
    target.updated_at = nowIso();
    return jsonResponse({ status: "ok", updated_at: target.updated_at });
  }

  if (zoneMatch && method === "DELETE") {
    const zoneId = zoneMatch[1];
    const index = mockState.zones.findIndex((entry) => entry.zone_id === zoneId);
    if (index < 0) {
      return jsonResponse({ detail: "Zone not found" }, 404);
    }
    const [removed] = mockState.zones.splice(index, 1);
    return jsonResponse({ status: "ok", deleted_at: removed.updated_at ?? nowIso() });
  }

  if (pathname === "/api/markers/symbols") {
    return jsonResponse(mockMarkerSymbols);
  }

  const markerPositionMatch = pathname.match(/^\/api\/markers\/(.+?)\/position$/);
  if (markerPositionMatch && method === "PATCH") {
    const markerId = markerPositionMatch[1];
    const body = (await parseBody(options.body)) as any;
    const target = mockState.markers.find((entry) => entry.object_destination_hash === markerId);
    if (!target) {
      return jsonResponse({ detail: "Marker not found" }, 404);
    }
    target.position = { lat: body?.lat ?? target.position.lat, lon: body?.lon ?? target.position.lon };
    target.time = nowIso();
    target.stale_at = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    target.updated_at = nowIso();
    return jsonResponse({ status: "ok", updated_at: target.updated_at });
  }

  const markerUpdateMatch = pathname.match(/^\/api\/markers\/(.+?)$/);
  if (markerUpdateMatch && method === "PATCH") {
    const markerId = markerUpdateMatch[1];
    const body = (await parseBody(options.body)) as any;
    const target = mockState.markers.find((entry) => entry.object_destination_hash === markerId);
    if (!target) {
      return jsonResponse({ detail: "Marker not found" }, 404);
    }
    const nextName = typeof body?.name === "string" ? body.name.trim() : "";
    if (!nextName) {
      return jsonResponse({ detail: "Marker name is required" }, 400);
    }
    target.name = nextName;
    target.time = nowIso();
    target.stale_at = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    target.updated_at = nowIso();
    return jsonResponse({ status: "ok", updated_at: target.updated_at });
  }

  if (pathname === "/api/v1/app/info") {
    return jsonResponse({
      name: "RCH UI",
      version: "1.35.0",
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
