// panel.js
// ------------------------------------------------------------
// The panel's BEHAVIOUR.
//
// The browser is an MQTT client connecting to Mosquitto over
// WebSocket (just like the Python devices):
//   1. It subscribes to "home/#" and updates the screen with incoming messages.
//   2. When a button is pressed it publishes a command to "<device topic>/command".
//
// Topic names and thresholds are not repeated in the code; panel.py
// reads them from config.py and serves them at "/config.json".
// ------------------------------------------------------------

"use strict";

// Labels shown on screen
const DISPLAY_NAME = {
  on: "On", off: "Off",
  open: "Open", closed: "Closed",
  cooling: "Cooling", heating: "Heating",
  disarmed: "Disarmed", armed: "Armed", triggered: "TRIGGERED!",
  detected: "Detected", clear: "Not detected",
  online: "Online", offline: "Offline",
};

const LOCALE = "en-GB";             // 24-hour clock, day/month dates
const CHART_POINT_COUNT = 90;       // Readings kept in the chart (2 s apart = 3 min)
const LOG_ROW_COUNT = 150;          // Max rows kept in the log
const SIMULATION_DURATION_MS = 4000; // Duration of a simulated motion/door event

let C = null;       // contents of config.json
let client = null;  // MQTT client

// The home's last state known to the panel (null = no news yet)
const home = {
  temperature: null,
  temperatureTime: null,
  outdoorTemperature: null,
  outdoorTemperatureTime: null,
  history: [],         // [{ v: temperature, o: outdoor temperature, a: AC state, t: reading time (ms) }]
  ac: null,
  lamp: null,
  motion: null,
  motionTime: null,    // When the motion state last changed
  door: null,
  alarm: null,
  times: {},           // { ac: ms, lamp: ms, ... } when the state message was produced on the device
  devices: {},         // { device_id: "online" | "offline" }
  topicDevice: {},     // { topic: device_id publishing to that topic }
};

const $ = (id) => document.getElementById(id);
const label = (state) => DISPLAY_NAME[state] ?? state ?? "—";

// ============================================================
// STARTUP
// ============================================================

async function start() {
  try {
    const response = await fetch("config.json");
    C = await response.json();
  } catch {
    brokerStatus("error", "Could not read config.json. Open the panel with 'python panel.py'.");
    return;
  }

  bindButtons();
  render();
  showEmptyLog();
  connect();

  // Update the "x s ago" texts every second
  setInterval(updateTimes, 1000);
  // Redraw the chart when the window is resized
  new ResizeObserver(drawChart).observe($("temperature-chart"));
}

// ============================================================
// MQTT CONNECTION
// ============================================================

function connect() {
  // We assume the broker is on whichever computer the page was opened from.
  const url = `ws://${location.hostname || "localhost"}:${C.websocket_port}`;

  client = mqtt.connect(url, {
    // Each tab gets its own ID (identical IDs would collide on the broker).
    clientId: "panel-" + Math.random().toString(16).slice(2, 8),
    clean: true,
    reconnectPeriod: 2000,  // If the connection drops, retry every 2 s
    connectTimeout: 5000,
  });

  client.on("connect", () => {
    brokerStatus("connected", "Connected to broker");
    client.subscribe(C.subscribe_topic, { qos: C.qos });
  });
  client.on("reconnect", () => brokerStatus("connecting", "Reconnecting…"));
  client.on("close", () => brokerStatus("disconnected", "No broker connection"));
  client.on("message", onMessage);
}

function brokerStatus(state, text) {
  $("broker-status").dataset.state = state;
  $("broker-text").textContent = text;
  // Command buttons can't be used without a connection
  document.querySelectorAll("button[data-device], #lamp-button, button[data-sim]")
    .forEach((b) => { b.disabled = state !== "connected"; });
}

/** Sends a command to an actuator, e.g. sendCommand("lamp", "on") */
function sendCommand(device, state) {
  const topic = C.topics[device] + C.command_suffix;
  publish(topic, { state, source: "panel" });
}

function publish(topic, data) {
  if (!client?.connected) return;
  const message = JSON.stringify({ ...data, timestamp: timestamp() });
  client.publish(topic, message, { qos: C.qos });
}

/**
 * Imitates a sensor event: publishes the "active" state first and the
 * "idle" state a few seconds later. It's the same message the real sensor
 * would send; the automation handles it like a real event.
 */
function simulate(button, sensor, active, idle) {
  const topic = C.topics[sensor];
  publish(topic, { state: active, source: "panel-simulation" });
  button.disabled = true;
  setTimeout(() => {
    publish(topic, { state: idle, source: "panel-simulation" });
    button.disabled = !client?.connected;
  }, SIMULATION_DURATION_MS);
}

// ============================================================
// INCOMING MESSAGES
// ============================================================

function onMessage(topic, payload, packet) {
  const text = new TextDecoder().decode(payload);
  const data = parseJson(text);
  // packet.retain = true means this is the "last known state" kept by the broker
  addToLog(topic, text, data, packet.retain);

  // Connection info: home/system/connection/<device_id>  ->  "online" / "offline"
  const root = C.connection_topic_root + "/";
  if (topic.startsWith(root)) {
    home.devices[topic.slice(root.length)] = text;
    renderDevices();
    renderOnlineTags();
    return;
  }

  if (!data || topic.endsWith(C.command_suffix)) return;  // Commands are only logged

  // Note which device publishes to this topic (for the offline warning)
  if (data.device_id) home.topicDevice[topic] = data.device_id;

  // When the message was produced on the device (or arrival time if missing).
  // For retained messages this is when the state really changed, not when the page opened.
  const time = messageTime(data);

  const T = C.topics;
  switch (topic) {
    case T.temperature:
      if (typeof data.temperature !== "number") return;
      home.temperature = data.temperature;
      home.temperatureTime = time;
      home.history.push({ v: data.temperature, o: home.outdoorTemperature, a: home.ac, t: time });
      if (home.history.length > CHART_POINT_COUNT) home.history.shift();
      break;
    case T.outdoor_temperature:
      if (typeof data.temperature !== "number") return;
      home.outdoorTemperature = data.temperature;
      home.outdoorTemperatureTime = time;
      break;
    case T.ac:    home.ac = data.state;    home.times.ac = time;    break;
    case T.lamp:  home.lamp = data.state;  home.times.lamp = time;  break;
    case T.door:  home.door = data.state;  home.times.door = time;  break;
    case T.alarm: home.alarm = data.state; home.times.alarm = time; break;
    case T.motion:
      // A retained message's time is the real change time too, so it can be shown right after the page opens
      if (data.state !== home.motion) home.motionTime = time;
      home.motion = data.state;
      break;
    default:
      return;
  }
  render();
  renderOnlineTags();
}

/** Converts the message's "timestamp" field (e.g. 2026-10-10T16:10:46) to milliseconds. */
function messageTime(data) {
  // The browser reads an ISO string without a time zone as local time (the Python side uses local time too)
  const ms = typeof data?.timestamp === "string" ? Date.parse(data.timestamp) : NaN;
  return Number.isNaN(ms) ? Date.now() : ms;
}

/** ms -> "16:10:46"; if not today, day/month is prefixed: "10/10 16:10:46" */
function formatTime(ms) {
  const t = new Date(ms);
  const clock = t.toLocaleTimeString(LOCALE);
  if (t.toDateString() === new Date().toDateString()) return clock;
  return t.toLocaleDateString(LOCALE, { day: "2-digit", month: "2-digit" }) + " " + clock;
}

function parseJson(text) {
  try {
    const v = JSON.parse(text);
    return v && typeof v === "object" && !Array.isArray(v) ? v : null;
  } catch {
    return null;
  }
}

// ============================================================
// UPDATING THE SCREEN
// ============================================================

function render() {
  // Temperature and AC
  $("temperature-value").textContent = home.temperature === null ? "--" : home.temperature.toFixed(1);
  $("outdoor-temperature-value").textContent =
    home.outdoorTemperature === null ? "--" : home.outdoorTemperature.toFixed(1);
  writeState("ac-state", home.ac);
  markSegment("ac", home.ac);

  // Lamp
  $("lamp-visual").dataset.state = home.lamp ?? "";
  writeState("lamp-state", home.lamp);
  $("lamp-button").textContent = home.lamp === "on" ? "Turn lamp off" : "Turn lamp on";

  // Motion and door
  writeState("motion-state", home.motion);
  writeState("door-state", home.door);

  // Alarm
  $("alarm-box").dataset.state = home.alarm ?? "";
  writeState("alarm-state", home.alarm);
  markSegment("alarm", home.alarm);

  updateTimes();
  drawChart();
}

function writeState(id, state) {
  const el = $(id);
  el.textContent = label(state);
  el.dataset.state = state ?? "";
}

/** Shows the option button matching the current state as "pressed". */
function markSegment(device, state) {
  document.querySelectorAll(`button[data-device="${device}"]`).forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.state === state));
  });
}

function updateTimes() {
  $("temperature-time").textContent = home.temperatureTime
    ? `Last reading ${formatTime(home.temperatureTime)} · ${timeAgo(home.temperatureTime)}`
    : "Waiting for data…";
  $("outdoor-temperature-time").textContent = home.outdoorTemperatureTime
    ? `Last reading ${formatTime(home.outdoorTemperatureTime)} · ${timeAgo(home.outdoorTemperatureTime)}`
    : "";

  // "Last update" lines on the actuator and door cards
  document.querySelectorAll("[data-time]").forEach((el) => {
    const t = home.times[el.dataset.time];
    el.textContent = t ? `Last update ${formatTime(t)} · ${timeAgo(t)}` : "";
  });

  let motionText = "";
  if (home.motionTime && home.motion === "detected") {
    motionText = `Started ${formatTime(home.motionTime)} · ${timeAgo(home.motionTime)}`;
  } else if (home.motionTime && home.motion === "clear") {
    const left = C.lamp_off_delay - Math.floor((Date.now() - home.motionTime) / 1000);
    motionText = `Last motion ${formatTime(home.motionTime)} · ${timeAgo(home.motionTime)}`;
    if (home.lamp === "on" && left > 0) motionText += ` · lamp turns off in ~${left} s`;
  }
  $("motion-time").textContent = motionText;
}

function timeAgo(time) {
  const s = Math.max(0, Math.round((Date.now() - time) / 1000));
  if (s < 2) return "just now";
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} days ago`;
}

/** If a sensor/device is offline, shows the small red tag on its card. */
function renderOnlineTags() {
  document.querySelectorAll("[data-online]").forEach((el) => {
    const deviceId = home.topicDevice[C.topics[el.dataset.online]];
    el.hidden = !(deviceId && home.devices[deviceId] === "offline");
  });
}

function renderDevices() {
  const list = $("device-list");
  const ids = Object.keys(home.devices).sort();
  list.replaceChildren(...ids.map((id) => {
    const li = document.createElement("li");
    li.dataset.state = home.devices[id];
    li.innerHTML = `<span class="dot"></span><span class="name"></span><span class="state"></span>`;
    li.querySelector(".name").textContent = id;
    li.querySelector(".state").textContent = label(home.devices[id]);
    return li;
  }));
}

// ============================================================
// TEMPERATURE CHART (hand-drawn SVG, no library)
// ============================================================

function drawChart() {
  const svg = $("temperature-chart");
  const w = svg.clientWidth, h = svg.clientHeight;  // width, height (pixels)
  if (!w || !C) return;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);

  const pad = { left: 34, right: 8, top: 10, bottom: 30 };  // margins (time labels at the bottom)
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;
  const E = C.ac_thresholds;
  const values = home.history.map((n) => n.v);
  const outdoorValues = home.history.map((n) => n.o).filter((v) => typeof v === "number");

  if (values.length < 2) {
    svg.innerHTML = `<text class="g-empty" x="${w / 2}" y="${h / 2}" text-anchor="middle">Waiting for readings to draw the chart…</text>`;
    return;
  }

  // Vertical axis range: cover the data, the outdoor temperature and the cooling thresholds
  const min = Math.floor(Math.min(...values, ...outdoorValues, E.cooling_stop) - 0.5);
  const max = Math.ceil(Math.max(...values, ...outdoorValues, E.cooling_start) + 0.5);
  const yPos = (v) => pad.top + plotH * (1 - (v - min) / (max - min));
  const xPos = (i) => pad.left + (plotW * i) / (CHART_POINT_COUNT - 1);

  let s = "";

  // Horizontal grid lines and left axis labels
  const step = max - min > 8 ? 2 : 1;
  for (let v = min; v <= max; v += step) {
    s += `<line class="g-grid" x1="${pad.left}" x2="${pad.left + plotW}" y1="${yPos(v)}" y2="${yPos(v)}"/>`;
    s += `<text class="g-axis-text" x="${pad.left - 6}" y="${yPos(v) + 4}" text-anchor="end">${v}°</text>`;
  }

  // Automation thresholds (those within range)
  const thresholds = [
    [E.cooling_start, "cooling starts"], [E.cooling_stop, "cooling stops"],
    [E.heating_start, "heating starts"], [E.heating_stop, "heating stops"],
  ];
  for (const [v] of thresholds) {
    if (v < min || v > max) continue;
    s += `<line class="g-threshold" x1="${pad.left}" x2="${pad.left + plotW}" y1="${yPos(v)}" y2="${yPos(v)}"/>`;
  }

  // Threshold labels are collected separately and added last.
  // In SVG what's drawn later appears on top, so the data line doesn't cover the text.
  let topLayer = "";
  for (const [v, text] of thresholds) {
    if (v < min || v > max) continue;
    topLayer += `<text class="g-threshold-text" x="${pad.left + 6}" y="${yPos(v) - 4}">${text} (${v}°)</text>`;
  }

  // Place the points so the newest reading is at the right edge
  const offset = CHART_POINT_COUNT - values.length;
  const points = home.history.map((n, i) => [xPos(i + offset), yPos(n.v)]);

  const baseY = pad.top + plotH;

  // The strip at the bottom: what the AC was doing at that moment
  const stripW = plotW / (CHART_POINT_COUNT - 1) + 0.5;
  home.history.forEach((n, i) => {
    if (n.a === "cooling" || n.a === "heating") {
      s += `<rect class="g-${n.a}" x="${xPos(i + offset) - stripW / 2}" y="${baseY + 3}" width="${stripW}" height="5"/>`;
    }
  });

  // Horizontal axis: a time label every 30 readings (≈1 min), going back from the newest
  for (let i = home.history.length - 1; i >= 0; i -= 30) {
    const px = xPos(i + offset);
    if (px < pad.left + 24) break;  // Don't collide with the left axis labels
    const anchor = i === home.history.length - 1 ? "end" : "middle";
    const clock = new Date(home.history[i].t).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    s += `<text class="g-axis-text" x="${px}" y="${h - 2}" text-anchor="${anchor}">${clock}</text>`;
  }

  // Outdoor temperature: dashed line (the line breaks where there is no data)
  let outdoorPath = "", penDown = false;
  home.history.forEach((n, i) => {
    if (typeof n.o !== "number") { penDown = false; return; }
    outdoorPath += `${penDown ? "L" : "M"}${xPos(i + offset).toFixed(1)},${yPos(n.o).toFixed(1)}`;
    penDown = true;
  });
  if (outdoorPath) s += `<path class="g-outdoor-line" d="${outdoorPath}"/>`;

  // Light fill under the line, and the temperature line
  const path = points.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join("");
  s += `<path class="g-area" d="${path}L${points.at(-1)[0]},${baseY}L${points[0][0]},${baseY}Z"/>`;
  s += `<path class="g-line" d="${path}"/>`;

  svg.innerHTML = s + topLayer;
}

// ============================================================
// EVENT LOG
// ============================================================

function addToLog(topic, text, data, retained) {
  // Temperature arrives every 2 s, so don't crowd the log unless asked
  const isReading = topic === C.topics.temperature || topic === C.topics.outdoor_temperature;
  if (isReading && !$("show-temperature").checked) return;

  const isCommand = topic.endsWith(C.command_suffix);
  let content;
  if (!data) content = label(text);
  else if (typeof data.temperature === "number") content = `${data.temperature} °C`;
  else if ("state" in data) content = label(data.state);
  else content = text;
  if (isCommand) content = `COMMAND → ${content}`;
  if (data?.source) content += `  (${data.source})`;

  const li = document.createElement("li");
  li.dataset.kind = isCommand ? "command" : "state";
  li.innerHTML = `<time></time><code></code><span class="content"></span>`;
  // The time shown is when the message was produced on the device (for retained messages, the real change time)
  const time = new Date(messageTime(data));
  li.querySelector("time").textContent = time.toLocaleTimeString(LOCALE);
  li.querySelector("time").dateTime = time.toISOString();
  li.querySelector("time").title = time.toLocaleString(LOCALE);
  // We use textContent so message content isn't interpreted as HTML (security)
  li.querySelector("code").textContent = topic;
  li.querySelector(".content").textContent = content;
  if (retained) {
    const r = document.createElement("span");
    r.className = "retained";
    r.textContent = "(retained last state)";
    li.querySelector(".content").append(r);
  }

  const log = $("log");
  log.querySelector(".empty")?.closest("li")?.remove();
  log.prepend(li);  // Newest message on top
  while (log.children.length > LOG_ROW_COUNT) log.lastElementChild.remove();
}

function showEmptyLog() {
  const log = $("log");
  if (!log.children.length) {
    log.innerHTML = `<li><span class="empty">No messages yet</span></li>`;
  }
}

// ============================================================
// BUTTONS
// ============================================================

function bindButtons() {
  // AC and alarm option buttons: read from the data-device / data-state attributes
  document.querySelectorAll("button[data-device]").forEach((b) => {
    b.addEventListener("click", () => sendCommand(b.dataset.device, b.dataset.state));
  });

  $("lamp-button").addEventListener("click", () => {
    sendCommand("lamp", home.lamp === "on" ? "off" : "on");
  });

  document.querySelectorAll("button[data-sim]").forEach((b) => {
    b.addEventListener("click", () => {
      if (b.dataset.sim === "motion") simulate(b, "motion", "detected", "clear");
      else simulate(b, "door", "open", "closed");
    });
  });

  $("clear-log").addEventListener("click", () => {
    $("log").replaceChildren();
    showEmptyLog();
  });
}

function timestamp() {
  // Same format as the Python side: 2026-10-10T16:10:46 (local time)
  const d = new Date();
  const two = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}` +
         `T${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`;
}

start();
