/* ── Dublin Bikes — main frontend script ── */

const DUBLIN = [53.3498, -6.2603];

// Initialise Leaflet map centred on Dublin
const map = L.map('map').setView(DUBLIN, 14);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

// Layer group so we can clear and re-add markers on refresh
const markerLayer = L.layerGroup().addTo(map);

/* ── Marker colour based on available bikes ── */
function markerColor(availBikes, status) {
  if (status !== 'OPEN') return '#95a5a6';   // grey — closed
  if (availBikes === 0)  return '#e74c3c';   // red — no bikes
  if (availBikes <= 5)   return '#f39c12';   // orange — few bikes
  return '#2ecc71';                          // green — many bikes
}

/* ── Build a circular Leaflet marker ── */
function makeMarker(station) {
  const avail  = station.available_bikes ?? 0;
  const stands = station.available_bike_stands ?? 0;
  const total  = avail + stands;
  const pct    = total > 0 ? Math.round((avail / total) * 100) : 0;
  const color  = markerColor(avail, station.status ?? 'OPEN');

  const marker = L.circleMarker(
    [station.position.lat, station.position.lng],
    { radius: 9, fillColor: color, color: '#fff', weight: 2, fillOpacity: 0.9 }
  );

  const updated = station.last_update
    ? new Date(station.last_update).toLocaleTimeString()
    : '—';

  marker.bindPopup(`
    <div class="popup-title">${station.name}</div>
    <div class="popup-row"><span>🚲 Available bikes</span><span>${avail}</span></div>
    <div class="popup-row"><span>🅿️ Free stands</span><span>${stands}</span></div>
    <div class="popup-row"><span>📦 Total capacity</span><span>${total}</span></div>
    <div class="avail-bar">
      <div class="avail-fill" style="width:${pct}%; background:${color};"></div>
    </div>
    <div class="popup-status">Status: ${station.status ?? '—'} · Updated: ${updated}</div>
  `);

  return marker;
}

/* ── Load bike station data from live JCDecaux API ── */
async function loadStations() {
  try {
    const res  = await fetch('/api/bikes');
    const json = await res.json();

    if (!res.ok) throw new Error(json.error ?? 'Unknown error');

    const stations = json.data ?? [];
    markerLayer.clearLayers();

    stations.forEach(s => makeMarker(s).addTo(markerLayer));

    document.getElementById('station-count').textContent =
      `${stations.length} stations loaded`;
  } catch (err) {
    document.getElementById('station-count').textContent =
      `Failed to load stations: ${err.message}`;
  }
}

/* ── Load weather from live OpenWeather API ── */
async function loadWeather() {
  const el = document.getElementById('weather-info');
  try {
    const res  = await fetch('/api/weather');
    const json = await res.json();

    if (!res.ok) throw new Error(json.error ?? 'Unknown error');

    const d    = json.data;
    const temp = d.main?.temp != null ? `${Math.round(d.main.temp)}°C` : '—';
    const feel = d.main?.feels_like != null ? `${Math.round(d.main.feels_like)}°C` : '—';
    const hum  = d.main?.humidity != null ? `${d.main.humidity}%` : '—';
    const wind = d.wind?.speed != null ? `${d.wind.speed} m/s` : '—';
    const desc = d.weather?.[0]?.description ?? '';
    const icon = d.weather?.[0]?.icon;

    const iconHtml = icon
      ? `<img src="https://openweathermap.org/img/wn/${icon}.png" alt="${desc}" title="${desc}" />`
      : '';

    el.innerHTML = `
      ${iconHtml}
      <span class="weather-item" title="Temperature">🌡️ ${temp}</span>
      <span class="weather-item" title="Feels like">Feels ${feel}</span>
      <span class="weather-item" title="Humidity">💧 ${hum}</span>
      <span class="weather-item" title="Wind speed">💨 ${wind}</span>
      ${desc ? `<span class="weather-item" style="opacity:0.85">${desc}</span>` : ''}
    `;
  } catch (err) {
    el.textContent = `Weather unavailable`;
  }
}

/* ── Refresh all data ── */
async function refresh() {
  const btn = document.getElementById('btn-refresh');
  btn.disabled = true;
  btn.textContent = '…';

  await Promise.all([loadWeather(), loadStations()]);

  btn.disabled = false;
  btn.textContent = '↻ Refresh';
}

// Wire up refresh button and load on startup
document.getElementById('btn-refresh').addEventListener('click', refresh);
refresh();
