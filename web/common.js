// Vox Libera — shared helpers for all pages.
// No build step, no frameworks. Loaded as a plain <script> tag.

const LANGUAGE_LABELS = {
  original: "Original",
  es: "Español",
  en: "English",
  pt: "Português",
};

function languageLabel(languageCode) {
  return LANGUAGE_LABELS[languageCode] || languageCode;
}

function formatDuration(totalSeconds) {
  if (typeof totalSeconds !== "number" || Number.isNaN(totalSeconds)) {
    return "0:00";
  }
  const wholeSeconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(wholeSeconds / 60);
  const seconds = wholeSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function formatCost(amountInUsd) {
  if (typeof amountInUsd !== "number" || Number.isNaN(amountInUsd)) {
    return "$0.000";
  }
  return `$${amountInUsd.toFixed(3)}`;
}

function buildWebSocketUrl(path) {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}${path}`;
}

async function fetchRooms() {
  const response = await fetch("/api/rooms");
  if (!response.ok) {
    throw new Error(`GET /api/rooms failed with status ${response.status}`);
  }
  return response.json();
}

async function fetchSamples() {
  const response = await fetch("/api/samples");
  if (!response.ok) {
    throw new Error(`GET /api/samples failed with status ${response.status}`);
  }
  return response.json();
}

async function simulateRoom(roomId, sampleFileName) {
  const response = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sample: sampleFileName }),
  });
  if (!response.ok) {
    throw new Error(`POST simulate failed with status ${response.status}`);
  }
  return response.json();
}

async function stopRoom(roomId) {
  const response = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/stop`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`POST stop failed with status ${response.status}`);
  }
  return response.json();
}

function exportUrl(roomId, format, languageCode) {
  const searchParameters = new URLSearchParams({ format, lang: languageCode });
  return `/api/rooms/${encodeURIComponent(roomId)}/export?${searchParameters.toString()}`;
}

/**
 * CaptionsClient — manages the audience WebSocket connection for a room:
 * connects, auto-reconnects with backoff, and keeps an upserted map of
 * segments plus the current interim text. Consumers subscribe via callbacks.
 *
 * On every reconnect the server resends full history, so the client
 * replaces its whole state rather than merging.
 */
class CaptionsClient {
  constructor(roomId) {
    this.roomId = roomId;
    this.socket = null;
    this.segmentsById = new Map();
    this.interimText = "";
    this.interimLanguage = null;
    this.roomStatus = "idle";
    this.reconnectAttempt = 0;
    this.reconnectTimerId = null;
    this.manuallyClosed = false;

    this.onHistoryReplaced = () => {};
    this.onSegmentUpserted = () => {};
    this.onInterimChanged = () => {};
    this.onStatusChanged = () => {};
    this.onConnectionChanged = () => {};
  }

  connect() {
    this.manuallyClosed = false;
    const webSocketUrl = buildWebSocketUrl(`/ws/rooms/${encodeURIComponent(this.roomId)}`);
    this.socket = new WebSocket(webSocketUrl);

    this.socket.addEventListener("open", () => {
      this.reconnectAttempt = 0;
      this.onConnectionChanged("connected");
    });

    this.socket.addEventListener("message", (event) => {
      this.handleMessage(event.data);
    });

    this.socket.addEventListener("close", () => {
      this.onConnectionChanged("disconnected");
      if (!this.manuallyClosed) {
        this.scheduleReconnect();
      }
    });

    this.socket.addEventListener("error", () => {
      this.socket.close();
    });

    this.onConnectionChanged("connecting");
  }

  handleMessage(rawData) {
    let message;
    try {
      message = JSON.parse(rawData);
    } catch (parseError) {
      return;
    }

    if (message.type === "history") {
      this.segmentsById = new Map();
      for (const segment of message.segments || []) {
        this.segmentsById.set(segment.id, segment);
      }
      this.interimText = "";
      this.interimLanguage = null;
      if (message.status) {
        this.roomStatus = message.status;
      }
      this.onHistoryReplaced(this.orderedSegments(), this.roomStatus);
      return;
    }

    if (message.type === "interim") {
      this.interimText = message.text || "";
      this.interimLanguage = message.language || null;
      this.onInterimChanged(this.interimText, this.interimLanguage);
      return;
    }

    if (message.type === "segment") {
      this.segmentsById.set(message.segment.id, message.segment);
      this.onSegmentUpserted(message.segment);
      return;
    }

    if (message.type === "status") {
      this.roomStatus = message.status;
      this.onStatusChanged(this.roomStatus);
      return;
    }
  }

  orderedSegments() {
    return Array.from(this.segmentsById.values()).sort((firstSegment, secondSegment) => {
      return firstSegment.id - secondSegment.id;
    });
  }

  scheduleReconnect() {
    this.reconnectAttempt += 1;
    const backoffMilliseconds = Math.min(1000 * 2 ** this.reconnectAttempt, 15000);
    this.onConnectionChanged("reconnecting");
    this.reconnectTimerId = setTimeout(() => {
      this.connect();
    }, backoffMilliseconds);
  }

  close() {
    this.manuallyClosed = true;
    if (this.reconnectTimerId) {
      clearTimeout(this.reconnectTimerId);
      this.reconnectTimerId = null;
    }
    if (this.socket) {
      this.socket.close();
    }
  }
}

const STATUS_LABELS = {
  idle: "Idle",
  starting: "Starting",
  live: "Live",
  rotating: "Rotating",
  error: "Error",
  stopped: "Stopped",
};

function statusLabel(statusCode) {
  return STATUS_LABELS[statusCode] || statusCode;
}
