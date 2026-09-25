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
  const response = await adminFetch(`/api/rooms/${encodeURIComponent(roomId)}/simulate`, {
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
  const response = await adminFetch(`/api/rooms/${encodeURIComponent(roomId)}/stop`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`POST stop failed with status ${response.status}`);
  }
  return response.json();
}

async function resetRoom(roomId) {
  const response = await adminFetch(`/api/rooms/${encodeURIComponent(roomId)}/reset`, {
    method: "POST",
  });
  if (!response.ok) {
    const responseText = await response.text().catch(() => "");
    const error = new Error(responseText || `POST reset failed with status ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function exportUrl(roomId, format, languageCode) {
  const searchParameters = new URLSearchParams({ format, lang: languageCode });
  return `/api/rooms/${encodeURIComponent(roomId)}/export?${searchParameters.toString()}`;
}

/**
 * Admin key helpers.
 *
 * The server may require an admin key for room-changing actions
 * (simulate, stop, reset, ingest). When required, `GET /api/rooms` reports
 * `admin_required: true`. REST calls send the key via the `X-Admin-Key`
 * header; the ingest WebSocket sends it as a `token` query parameter.
 */
const ADMIN_KEY_STORAGE_KEY = "voxlibera.adminKey";

function getAdminKey() {
  try {
    return localStorage.getItem(ADMIN_KEY_STORAGE_KEY) || "";
  } catch (storageError) {
    return "";
  }
}

function setAdminKey(adminKey) {
  try {
    if (adminKey) {
      localStorage.setItem(ADMIN_KEY_STORAGE_KEY, adminKey);
    } else {
      localStorage.removeItem(ADMIN_KEY_STORAGE_KEY);
    }
  } catch (storageError) {
    // Ignore storage failures (private browsing, quota, etc.)
  }
}

function promptForAdminKey(promptMessage) {
  const enteredKey = window.prompt(promptMessage || t("common.enterAdminKey"));
  const trimmedKey = (enteredKey || "").trim();
  setAdminKey(trimmedKey);
  return trimmedKey;
}

/**
 * fetch() wrapper that attaches the admin key header and retries once
 * after prompting the operator if the server responds with 401.
 */
async function adminFetch(url, options) {
  const requestOptions = Object.assign({}, options || {});
  const headers = new Headers(requestOptions.headers || {});
  const adminKey = getAdminKey();
  if (adminKey) {
    headers.set("X-Admin-Key", adminKey);
  }
  requestOptions.headers = headers;

  let response = await fetch(url, requestOptions);
  if (response.status === 401) {
    const enteredKey = promptForAdminKey(t("common.adminKeyNeeded"));
    if (enteredKey) {
      headers.set("X-Admin-Key", enteredKey);
      requestOptions.headers = headers;
      response = await fetch(url, requestOptions);
    }
  }
  return response;
}

/**
 * Wires a small "Admin key" button that lets the operator set, change, or
 * clear the stored admin key. Safe to call even when no key is required.
 */
function setupAdminKeyButton(buttonElement) {
  buttonElement.addEventListener("click", () => {
    const currentAdminKey = getAdminKey();
    const enteredKey = window.prompt(
      t("common.adminKeyPromptLabel"),
      currentAdminKey
    );
    if (enteredKey === null) {
      return;
    }
    setAdminKey(enteredKey.trim());
  });
}

/**
 * Renders the shared top navigation bar into the element with
 * id="top-navigation". `activePage` is one of "captions", "broadcast",
 * "dashboard".
 */
// While a page must stay open (e.g. broadcast.html capturing audio), navigating away
// in the same tab would kill it: the nav then opens pages in a new tab instead.
let keepPageAlive = false;
let lastRenderedNavigationPage = null;
let pageTranslationsApplied = false;

function setKeepPageAlive(enabled) {
  keepPageAlive = enabled;
  if (lastRenderedNavigationPage) {
    renderTopNavigation(lastRenderedNavigationPage);
  }
}

function renderTopNavigation(activePage) {
  const container = document.getElementById("top-navigation");
  if (!container) {
    return;
  }
  lastRenderedNavigationPage = activePage;

  const headerElement = document.createElement("header");
  headerElement.className = "top-nav";

  const innerElement = document.createElement("div");
  innerElement.className = "top-nav-inner";

  const wordmarkElement = document.createElement("span");
  wordmarkElement.className = "top-nav-wordmark";
  wordmarkElement.textContent = "Vox Libera";
  innerElement.appendChild(wordmarkElement);

  const navigationElement = document.createElement("nav");
  navigationElement.className = "top-nav-links";

  const pages = [
    { key: "captions", labelKey: "nav.captions", href: "/" },
    { key: "broadcast", labelKey: "nav.broadcast", href: "/broadcast.html" },
    { key: "dashboard", labelKey: "nav.dashboard", href: "/dashboard.html" },
  ];

  for (const page of pages) {
    const linkElement = document.createElement("a");
    linkElement.className = "top-nav-link";
    if (page.key === activePage) {
      linkElement.classList.add("top-nav-link--active");
      linkElement.setAttribute("aria-current", "page");
    }
    linkElement.href = page.href;
    linkElement.textContent = t(page.labelKey);
    if (keepPageAlive && page.key !== activePage) {
      linkElement.target = "_blank";
      linkElement.rel = "noopener";
      linkElement.title = t("nav.opensInNewTab");
    }
    navigationElement.appendChild(linkElement);
  }

  innerElement.appendChild(navigationElement);
  if (keepPageAlive) {
    const onAirElement = document.createElement("span");
    onAirElement.className = "top-nav-on-air";
    onAirElement.textContent = t("nav.onAir");
    innerElement.appendChild(onAirElement);
  }
  innerElement.appendChild(buildLanguageToggle(activePage));
  headerElement.appendChild(innerElement);

  container.innerHTML = "";
  container.appendChild(headerElement);
  // Static page text (data-i18n) must follow the chosen language on load, not only after a toggle.
  // Only on the first render: later re-renders (e.g. going on air) must not overwrite text that
  // the page changed dynamically, like the Start/Stop button. The EN|ES toggle re-applies itself.
  if (!pageTranslationsApplied) {
    pageTranslationsApplied = true;
    applyTranslations(document);
  }
}

/**
 * Compact EN | ES toggle rendered in the shared top navigation. Switching
 * language re-renders the navigation itself, re-applies data-i18n
 * translations across the document, and calls the page's own
 * window.onUiLanguageChanged() hook (if defined) so dynamically built
 * content — room cards, buttons, status text — refreshes immediately
 * without a page reload.
 */
function buildLanguageToggle(activePage) {
  const toggleElement = document.createElement("div");
  toggleElement.className = "top-nav-language-toggle";

  const currentUiLanguage = getUiLanguage();
  const languageOptions = [
    { code: "en", label: "EN", name: "English" },
    { code: "es", label: "ES", name: "Español" },
  ];

  for (const languageOption of languageOptions) {
    const languageButtonElement = document.createElement("button");
    languageButtonElement.type = "button";
    languageButtonElement.className = "top-nav-language-button";
    if (languageOption.code === currentUiLanguage) {
      languageButtonElement.classList.add("top-nav-language-button--active");
    }
    languageButtonElement.textContent = languageOption.label;
    languageButtonElement.setAttribute(
      "aria-label",
      t("nav.switchLanguage", { language: languageOption.name })
    );
    languageButtonElement.addEventListener("click", () => {
      if (languageOption.code === getUiLanguage()) {
        return;
      }
      setUiLanguage(languageOption.code);
      renderTopNavigation(activePage);
      applyTranslations(document);
      if (typeof window.onUiLanguageChanged === "function") {
        window.onUiLanguageChanged();
      }
    });
    toggleElement.appendChild(languageButtonElement);
  }

  return toggleElement;
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

function statusLabel(statusCode) {
  const statusKey = `status.${statusCode}`;
  const translatedLabel = t(statusKey);
  return translatedLabel === statusKey ? statusCode : translatedLabel;
}
