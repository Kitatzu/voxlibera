// Vox Libera — internationalization (English / Spanish).
// No build step, no frameworks. Loaded as a plain <script> tag, before
// common.js, on every page. Provides:
//   - t(key, params, languageCodeOverride)
//   - getUiLanguage() / setUiLanguage(languageCode)
//   - applyTranslations(root = document, languageCodeOverride)
//
// Data (room names, room descriptions, caption text, sample file names) is
// never translated by this module — only static UI copy lives here.

const UI_LANGUAGE_STORAGE_KEY = "voxlibera.uiLanguage";
const DEFAULT_UI_LANGUAGE = "en";

const translations = {
  en: {
    "nav.captions": "Captions",
    "nav.broadcast": "Broadcast",
    "nav.dashboard": "Dashboard",
    "nav.onAir": "● On air",
    "nav.opensInNewTab": "Opens in a new tab so the broadcast keeps running",
    "nav.switchLanguage": "Switch to {language}",

    "common.adminKeyButton": "🔑 Admin key",
    "common.enterAdminKey": "Enter the admin key",
    "common.adminKeyPromptLabel": "Admin key (leave blank to clear):",
    "common.adminKeyNeeded": "This action needs the admin key. Enter it:",
    "common.wrongAdminKeyPrompt": "Wrong admin key. Enter the correct key:",
    "common.couldNotReachServer": "Could not reach the server. Check your connection and reload.",
    "common.copied": "Copied!",

    "status.idle": "Idle",
    "status.starting": "Starting",
    "status.live": "Live",
    "status.rotating": "Rotating",
    "status.error": "Error",
    "status.stopped": "Stopped",

    "connection.connecting": "Connecting…",
    "connection.connected": "Connected",
    "connection.reconnecting": "Reconnecting…",
    "connection.disconnected": "Disconnected",
    "connection.live": "Live",

    "index.title": "Vox Libera — Live Captions",
    "index.pickRoomAndLanguage": "Pick a room and a language to see live captions.",
    "index.roomLabel": "Room",
    "index.languageLabel": "Language",
    "index.join": "Join",
    "index.roomNameDefault": "Room",
    "index.changeRoom": "Change room",
    "index.decreaseFontSize": "Decrease font size",
    "index.increaseFontSize": "Increase font size",
    "index.jumpToLive": "Jump to live",
    "index.clearScreen": "🧹 Clear screen",
    "index.clearScreenHint": "Hide the captions shown so far. Only on this screen: nothing is deleted.",
    "index.screenCleared": "Screen cleared. The full transcript is still in the downloads.",
    "index.showAllCaptions": "Show everything again",
    "index.roomStatus": "Room status: {status}",
    "index.interimTranslating": "{text} (original, translating…)",

    "broadcast.title": "Vox Libera — Broadcast",
    "broadcast.heading": "Broadcast",
    "broadcast.subtitle": "Send this device's audio to a room, from the browser.",
    "broadcast.step1": "1. Pick the room",
    "broadcast.step2": "2. Pick the audio source",
    "broadcast.microphone": "Microphone",
    "broadcast.tabOrScreenAudio": "Tab or screen audio",
    "broadcast.audioFile": "Audio file",
    "broadcast.microphoneLabel": "Microphone",
    "broadcast.step3": "3. Broadcast",
    "broadcast.startBroadcasting": "Start broadcasting",
    "broadcast.stoppedFromDashboard": "This broadcast was stopped from the dashboard.",
    "broadcast.stop": "Stop",
    "broadcast.elapsed": "Elapsed",
    "broadcast.connectionLabel": "Connection",
    "broadcast.inputLevel": "Input level",
    "broadcast.noAudioDetected": "No audio detected. Check the source is actually producing sound.",
    "broadcast.reconnect": "Reconnect",
    "broadcast.liveCaptionPreview": "Live caption preview",
    "broadcast.openAudienceView": "Open audience view",
    "broadcast.copyAudienceLink": "📋 Copy audience link",
    "broadcast.selectedRoom": "Selected room: {name}",
    "broadcast.alreadyLive": "Already live",
    "broadcast.microphoneAccessError": "Could not access the microphone. Check browser permissions.",
    "broadcast.microphoneSwitchError": "Could not switch to that microphone.",
    "broadcast.microphoneDefaultLabel": "Microphone",
    "broadcast.tabSharingCancelled": "Screen or tab sharing was cancelled.",
    "broadcast.shareTabAudioHint": "Share a tab and tick 'Share tab audio'.",
    "broadcast.tabAudioCaptured": "Tab/screen audio captured.",
    "broadcast.selectedFile": "Selected file: {name}",
    "broadcast.audioPipelineError": "Could not set up the audio pipeline for this source.",
    "broadcast.wrongAdminKey": "Wrong admin key.",
    "broadcast.someoneAlreadyBroadcasting": "Someone is already broadcasting to this room.",
    "broadcast.unknownRoom": "Unknown room.",
    "broadcast.serverClosedConnection": "The server closed the connection.",
    "broadcast.connectionClosedCode": "Connection closed (code {code}).",

    "dashboard.title": "Vox Libera — Dashboard",
    "dashboard.heading": "Dashboard",
    "dashboard.subtitle": "Live monitoring, refreshed every 2 seconds.",
    "dashboard.couldNotReachServerRetrying": "Could not reach the server. Retrying…",
    "dashboard.noRoomsConfigured": "No rooms configured.",
    "dashboard.totalEstimatedCost": "Total estimated cost: {cost}",
    "dashboard.source": "Source",
    "dashboard.connectedKind": "Connected ({kind})",
    "dashboard.unknownKind": "unknown",
    "dashboard.disconnected": "Disconnected",
    "dashboard.audioTime": "Audio time",
    "dashboard.segments": "Segments",
    "dashboard.subscribers": "Subscribers",
    "dashboard.sessionsOpened": "Sessions opened",
    "dashboard.rotations": "Rotations",
    "dashboard.errors": "Errors",
    "dashboard.captionLag": "Caption lag",
    "dashboard.translationLatency": "Translation latency",
    "dashboard.estimatedCost": "Estimated cost",
    "dashboard.lastHeard": "Last heard",
    "dashboard.nothingHeardYet": "Nothing heard yet.",
    "dashboard.lastError": "Last error: {error}",
    "dashboard.playSample": "▶ Play sample",
    "dashboard.failedToStartSimulation": "Failed to start simulation: {message}",
    "dashboard.broadcast": "🎙 Broadcast",
    "dashboard.stop": "■ Stop",
    "dashboard.failedToStop": "Failed to stop: {message}",
    "dashboard.clearTranscript": "🗑 Clear transcript",
    "dashboard.confirmDeleteTranscript": "Delete this room's transcript?",
    "dashboard.failedToClearTranscript": "Failed to clear transcript: {message}",
    "dashboard.openCaptions": "👁 Open captions",
    "dashboard.copyAudienceLink": "📋 Copy audience link",
    "dashboard.copyObsLink": "📋 Copy OBS link",
    "dashboard.downloadSrt": "⬇ SRT",
    "dashboard.downloadVtt": "⬇ VTT",
    "dashboard.downloadTxt": "⬇ TXT",

    "obs.title": "Vox Libera — OBS Overlay",
    "obs.helpTitle": "Vox Libera — OBS overlay",
    "obs.helpUsage":
      'Add <code>room</code> as a query parameter to use this as a browser source, e.g. <code>obs.html?room=main-stage&amp;lang=es&amp;lines=2&amp;size=42&amp;position=bottom</code>',
    "obs.helpParams":
      'Parameters: <code>room</code> (required), <code>lang</code> (default <code>es</code>), <code>lines</code> (default 2), <code>size</code> (font px, default 42), <code>position</code> (<code>bottom</code> or <code>top</code>, default <code>bottom</code>).',
  },
  es: {
    "nav.captions": "Subtítulos",
    "nav.broadcast": "Transmitir",
    "nav.dashboard": "Panel",
    "nav.onAir": "● Al aire",
    "nav.opensInNewTab": "Se abre en otra pestaña para que la transmisión siga",
    "nav.switchLanguage": "Cambiar a {language}",

    "common.adminKeyButton": "🔑 Clave de administrador",
    "common.enterAdminKey": "Ingresa la clave de administrador",
    "common.adminKeyPromptLabel": "Clave de administrador (dejar en blanco para borrarla):",
    "common.adminKeyNeeded": "Esta acción necesita la clave de administrador. Ingresala:",
    "common.wrongAdminKeyPrompt": "Clave de administrador incorrecta. Ingresa la clave correcta:",
    "common.couldNotReachServer": "No se pudo conectar con el servidor. Revisa tu conexión y recarga la página.",
    "common.copied": "¡Copiado!",

    "status.idle": "Inactivo",
    "status.starting": "Iniciando",
    "status.live": "En vivo",
    "status.rotating": "Rotando sesión",
    "status.error": "Error",
    "status.stopped": "Detenido",

    "connection.connecting": "Conectando…",
    "connection.connected": "Conectado",
    "connection.reconnecting": "Reconectando…",
    "connection.disconnected": "Desconectado",
    "connection.live": "En vivo",

    "index.title": "Vox Libera — Subtítulos en vivo",
    "index.pickRoomAndLanguage": "Elige una sala y un idioma para ver los subtítulos en vivo.",
    "index.roomLabel": "Sala",
    "index.languageLabel": "Idioma",
    "index.join": "Unirme",
    "index.roomNameDefault": "Sala",
    "index.changeRoom": "Cambiar de sala",
    "index.decreaseFontSize": "Reducir tamaño de letra",
    "index.increaseFontSize": "Aumentar tamaño de letra",
    "index.jumpToLive": "Ir al en vivo",
    "index.clearScreen": "🧹 Limpiar pantalla",
    "index.clearScreenHint": "Oculta los subtítulos mostrados hasta ahora. Solo en esta pantalla: no se borra nada.",
    "index.screenCleared": "Pantalla limpia. La transcripción completa sigue disponible en las descargas.",
    "index.showAllCaptions": "Mostrar todo de nuevo",
    "index.roomStatus": "Estado de la sala: {status}",
    "index.interimTranslating": "{text} (original, traduciendo…)",

    "broadcast.title": "Vox Libera — Transmisión",
    "broadcast.heading": "Transmitir",
    "broadcast.subtitle": "Envía el audio de este dispositivo a una sala, desde el navegador.",
    "broadcast.step1": "1. Elige la sala",
    "broadcast.step2": "2. Elige la fuente de audio",
    "broadcast.microphone": "Micrófono",
    "broadcast.tabOrScreenAudio": "Audio de pestaña o pantalla",
    "broadcast.audioFile": "Archivo de audio",
    "broadcast.microphoneLabel": "Micrófono",
    "broadcast.step3": "3. Transmitir",
    "broadcast.startBroadcasting": "Transmitir",
    "broadcast.stoppedFromDashboard": "Esta transmisión se detuvo desde el panel.",
    "broadcast.stop": "Detener",
    "broadcast.elapsed": "Tiempo transcurrido",
    "broadcast.connectionLabel": "Conexión",
    "broadcast.inputLevel": "Nivel de entrada",
    "broadcast.noAudioDetected": "Sin audio detectado. Revisa que la fuente esté produciendo sonido.",
    "broadcast.reconnect": "Reconectar",
    "broadcast.liveCaptionPreview": "Vista previa de subtítulos en vivo",
    "broadcast.openAudienceView": "Abrir vista del público",
    "broadcast.copyAudienceLink": "📋 Copiar link para el público",
    "broadcast.selectedRoom": "Sala seleccionada: {name}",
    "broadcast.alreadyLive": "Ya está en vivo",
    "broadcast.microphoneAccessError": "No se pudo acceder al micrófono. Revisa los permisos del navegador.",
    "broadcast.microphoneSwitchError": "No se pudo cambiar a ese micrófono.",
    "broadcast.microphoneDefaultLabel": "Micrófono",
    "broadcast.tabSharingCancelled": "Se canceló el uso compartido de pantalla o pestaña.",
    "broadcast.shareTabAudioHint": "Comparte una pestaña y marca 'Compartir audio de la pestaña'.",
    "broadcast.tabAudioCaptured": "Audio de pestaña o pantalla capturado.",
    "broadcast.selectedFile": "Archivo seleccionado: {name}",
    "broadcast.audioPipelineError": "No se pudo configurar el flujo de audio para esta fuente.",
    "broadcast.wrongAdminKey": "Clave de administrador incorrecta.",
    "broadcast.someoneAlreadyBroadcasting": "Ya hay alguien transmitiendo a esta sala.",
    "broadcast.unknownRoom": "Sala desconocida.",
    "broadcast.serverClosedConnection": "El servidor cerró la conexión.",
    "broadcast.connectionClosedCode": "Conexión cerrada (código {code}).",

    "dashboard.title": "Vox Libera — Panel",
    "dashboard.heading": "Panel",
    "dashboard.subtitle": "Monitoreo en vivo, actualizado cada 2 segundos.",
    "dashboard.couldNotReachServerRetrying": "No se pudo conectar con el servidor. Reintentando…",
    "dashboard.noRoomsConfigured": "No hay salas configuradas.",
    "dashboard.totalEstimatedCost": "Costo total estimado: {cost}",
    "dashboard.source": "Fuente",
    "dashboard.connectedKind": "Conectado ({kind})",
    "dashboard.unknownKind": "desconocida",
    "dashboard.disconnected": "Desconectado",
    "dashboard.audioTime": "Tiempo de audio",
    "dashboard.segments": "Segmentos",
    "dashboard.subscribers": "Suscriptores",
    "dashboard.sessionsOpened": "Sesiones abiertas",
    "dashboard.rotations": "Rotaciones",
    "dashboard.errors": "Errores",
    "dashboard.captionLag": "Retraso de subtítulos",
    "dashboard.translationLatency": "Latencia de traducción",
    "dashboard.estimatedCost": "Costo estimado",
    "dashboard.lastHeard": "Última frase escuchada",
    "dashboard.nothingHeardYet": "Todavía no se escuchó nada.",
    "dashboard.lastError": "Último error: {error}",
    "dashboard.playSample": "▶ Reproducir ejemplo",
    "dashboard.failedToStartSimulation": "No se pudo iniciar la simulación: {message}",
    "dashboard.broadcast": "🎙 Transmitir",
    "dashboard.stop": "■ Detener",
    "dashboard.failedToStop": "No se pudo detener: {message}",
    "dashboard.clearTranscript": "🗑 Borrar transcripción",
    "dashboard.confirmDeleteTranscript": "¿Borrar la transcripción de esta sala?",
    "dashboard.failedToClearTranscript": "No se pudo borrar la transcripción: {message}",
    "dashboard.openCaptions": "👁 Ver subtítulos",
    "dashboard.copyAudienceLink": "📋 Copiar link para el público",
    "dashboard.copyObsLink": "📋 Copiar link para OBS",
    "dashboard.downloadSrt": "⬇ SRT",
    "dashboard.downloadVtt": "⬇ VTT",
    "dashboard.downloadTxt": "⬇ TXT",

    "obs.title": "Vox Libera — Superposición para OBS",
    "obs.helpTitle": "Vox Libera — superposición para OBS",
    "obs.helpUsage":
      'Agrega <code>room</code> como parámetro de consulta para usar esto como fuente de navegador, por ejemplo <code>obs.html?room=main-stage&amp;lang=es&amp;lines=2&amp;size=42&amp;position=bottom</code>',
    "obs.helpParams":
      'Parámetros: <code>room</code> (obligatorio), <code>lang</code> (por defecto <code>es</code>), <code>lines</code> (por defecto 2), <code>size</code> (tamaño de fuente en px, por defecto 42), <code>position</code> (<code>bottom</code> o <code>top</code>, por defecto <code>bottom</code>).',
  },
};

function getUiLanguage() {
  try {
    const storedLanguage = localStorage.getItem(UI_LANGUAGE_STORAGE_KEY);
    if (storedLanguage === "en" || storedLanguage === "es") {
      return storedLanguage;
    }
  } catch (storageError) {
    // Ignore storage failures (private browsing, quota, etc.) and fall through.
  }

  try {
    if (navigator.language && navigator.language.toLowerCase().startsWith("es")) {
      return "es";
    }
  } catch (navigatorError) {
    // Ignore and fall through to the default.
  }

  return DEFAULT_UI_LANGUAGE;
}

function setUiLanguage(languageCode) {
  try {
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, languageCode);
  } catch (storageError) {
    // Ignore storage failures (private browsing, quota, etc.)
  }
}

function interpolateTranslationParams(template, params) {
  if (!params) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (matchedPlaceholder, paramName) => {
    return Object.prototype.hasOwnProperty.call(params, paramName)
      ? String(params[paramName])
      : matchedPlaceholder;
  });
}

function t(key, params, languageCodeOverride) {
  const languageCode = languageCodeOverride || getUiLanguage();
  const languageDictionary = translations[languageCode] || translations[DEFAULT_UI_LANGUAGE];
  const fallbackDictionary = translations[DEFAULT_UI_LANGUAGE];

  let template;
  if (languageDictionary && Object.prototype.hasOwnProperty.call(languageDictionary, key)) {
    template = languageDictionary[key];
  } else if (fallbackDictionary && Object.prototype.hasOwnProperty.call(fallbackDictionary, key)) {
    template = fallbackDictionary[key];
  } else {
    template = key;
  }

  return interpolateTranslationParams(template, params);
}

/**
 * Fills every element under `root` that declares a data-i18n* attribute.
 *
 * - data-i18n            -> element.textContent
 * - data-i18n-html        -> element.innerHTML (trusted, authored strings only — never user/room data)
 * - data-i18n-placeholder -> element.placeholder
 * - data-i18n-title       -> element.title
 * - data-i18n-aria-label  -> element.aria-label
 *
 * Also sets document.documentElement.lang when applying to the whole document.
 */
function applyTranslations(root, languageCodeOverride) {
  const rootElement = root || document;
  const languageCode = languageCodeOverride || getUiLanguage();

  for (const element of rootElement.querySelectorAll("[data-i18n]")) {
    element.textContent = t(element.getAttribute("data-i18n"), undefined, languageCode);
  }
  for (const element of rootElement.querySelectorAll("[data-i18n-html]")) {
    element.innerHTML = t(element.getAttribute("data-i18n-html"), undefined, languageCode);
  }
  for (const element of rootElement.querySelectorAll("[data-i18n-placeholder]")) {
    element.setAttribute(
      "placeholder",
      t(element.getAttribute("data-i18n-placeholder"), undefined, languageCode)
    );
  }
  for (const element of rootElement.querySelectorAll("[data-i18n-title]")) {
    element.setAttribute("title", t(element.getAttribute("data-i18n-title"), undefined, languageCode));
  }
  for (const element of rootElement.querySelectorAll("[data-i18n-aria-label]")) {
    element.setAttribute(
      "aria-label",
      t(element.getAttribute("data-i18n-aria-label"), undefined, languageCode)
    );
  }

  if (rootElement === document) {
    document.documentElement.lang = languageCode;
  }
}
