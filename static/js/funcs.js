/* Shared ViewLRPT helpers. No framework or build step is required. */
(function () {
  "use strict";

  const API_BASE = "/api";

  const DEMO_OBSERVATIONS = [
    { id: "demo-20261010-1234", satellite_name: "METEOR-M 2-3", norad_id: 57166, timestamp_utc: "2026-10-10T12:34:00Z", line_count: 15082 },
    { id: "demo-20261010-1105", satellite_name: "METEOR-M 2-3", norad_id: 57166, timestamp_utc: "2026-10-10T11:05:00Z", line_count: 14761 },
    { id: "demo-20261009-2241", satellite_name: "METEOR-M 2-3", norad_id: 57166, timestamp_utc: "2026-10-09T22:41:00Z", line_count: 15304 },
    { id: "demo-20261009-1918", satellite_name: "METEOR-M 2-3", norad_id: 57166, timestamp_utc: "2026-10-09T19:18:00Z", line_count: 14990 },
    { id: "demo-20261009-1530", satellite_name: "METEOR-M 2-3", norad_id: 57166, timestamp_utc: "2026-10-09T15:30:00Z", line_count: 15128 },
    { id: "demo-20261008-2333", satellite_name: "METEOR-M 2-3", norad_id: 57166, timestamp_utc: "2026-10-08T23:33:00Z", line_count: 14590 },
    { id: "demo-20261008-1802", satellite_name: "METEOR-M 2-3", norad_id: 57166, timestamp_utc: "2026-10-08T18:02:00Z", line_count: 15241 },
    { id: "demo-20261007-1210", satellite_name: "METEOR-M 2-3", norad_id: 57166, timestamp_utc: "2026-10-07T12:10:00Z", line_count: 14876 }
  ];

  function cloneDemoObservations() {
    return DEMO_OBSERVATIONS.map(function (item) { return Object.assign({}, item); });
  }

  function formatUtc(value, includeSeconds) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value || "—");
    const iso = date.toISOString();
    return includeSeconds === false ? iso.slice(0, 16).replace("T", " ") : iso.slice(0, 19).replace("T", " ");
  }

  function formatInteger(value) {
    const number = Number(value);
    return Number.isFinite(number) ? new Intl.NumberFormat("en-US").format(number) : "—";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char];
    });
  }

  function mockImageDataUri(options) {
    const opts = options || {};
    const width = opts.thumbnail ? 320 : 960;
    const height = opts.thumbnail ? 210 : 640;
    const seed = Math.abs(Number(opts.seed || 1)) || 1;
    const label = escapeHtml(opts.label || "LRPT");
    const rotation = opts.rotate180 ? "rotate(180 480 320)" : "";
    const mapOverlay = opts.showMap ? [
      '<g fill="none" stroke="#7dc5ec" stroke-width="2" opacity=".9">',
      '<path d="M30 180 Q180 80 330 175 T640 150 T930 190"/>',
      '<path d="M20 330 Q190 260 365 345 T690 300 T940 355"/>',
      '<path d="M180 30 Q250 180 205 320 T220 610"/>',
      '<path d="M480 20 Q430 170 500 330 T470 620"/>',
      '<path d="M760 35 Q690 210 760 370 T735 610"/>',
      '</g>'
    ].join("") : "";
    const cityOverlay = opts.showCityLabels ? [
      '<g fill="#ffe08a" stroke="#222" stroke-width="1" font-family="Arial, sans-serif" font-size="20">',
      '<circle cx="280" cy="240" r="5"/><text x="292" y="235" stroke="none">CITY A</text>',
      '<circle cx="610" cy="385" r="5"/><text x="622" y="380" stroke="none">CITY B</text>',
      '<circle cx="760" cy="180" r="5"/><text x="772" y="175" stroke="none">CITY C</text>',
      '</g>'
    ].join("") : "";
    const gridOverlay = opts.geocorrection ? '<path d="M0 160 H960 M0 320 H960 M0 480 H960 M240 0 V640 M480 0 V640 M720 0 V640" stroke="#d7e0e6" stroke-width="1" opacity=".45" fill="none"/>' : "";
    const svg = [
      '<svg xmlns="http://www.w3.org/2000/svg" width="', width, '" height="', height, '" viewBox="0 0 960 640">',
      '<defs>',
      '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1b1f22"/><stop offset=".55" stop-color="#747b7d"/><stop offset="1" stop-color="#d1d5d5"/></linearGradient>',
      '<pattern id="scan" width="4" height="6" patternUnits="userSpaceOnUse"><rect width="4" height="2" fill="#000" opacity=".1"/></pattern>',
      '<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".025 .08" numOctaves="2" seed="', seed, '"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="table" tableValues="0 .28"/></feComponentTransfer></filter>',
      '</defs>',
      '<rect width="960" height="640" fill="#161a1c"/>',
      '<g transform="', rotation, '">',
      '<rect x="16" y="16" width="928" height="608" fill="url(#bg)"/>',
      '<path d="M15 105 Q100 42 188 110 T370 98 T565 120 T755 65 T945 110 L945 250 Q830 300 725 245 T520 255 T300 225 T15 275Z" fill="#d8dcda" opacity=".72"/>',
      '<path d="M15 350 Q110 285 240 362 T440 350 T650 385 T945 330 L945 465 Q820 530 680 455 T420 500 T225 470 T15 515Z" fill="#333a3c" opacity=".82"/>',
      '<path d="M90 180 Q180 130 240 190 T390 185 T520 170 T700 210 T900 165" fill="none" stroke="#f4f5f4" stroke-width="24" opacity=".25"/>',
      '<path d="M70 430 Q190 360 280 440 T470 445 T650 420 T890 455" fill="none" stroke="#f6f6f6" stroke-width="34" opacity=".2"/>',
      '<rect x="16" y="16" width="928" height="608" filter="url(#grain)" opacity=".5"/>',
      '</g>',
      '<rect x="16" y="16" width="928" height="608" fill="url(#scan)" opacity=".35"/>',
      gridOverlay, mapOverlay, cityOverlay,
      '<rect x="20" y="20" width="200" height="34" fill="#101416" opacity=".82"/>',
      '<text x="34" y="43" font-family="Arial, sans-serif" font-size="18" fill="#fff">', label, '</text>',
      '<text x="930" y="610" text-anchor="end" font-family="Arial, sans-serif" font-size="14" fill="#fff" opacity=".8">MOCK DATA</text>',
      '</svg>'
    ].join("");
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  }

  function thumbnailUrl(observation, channel) {
    const thumbnails = observation && observation.thumbnails;
    if (Array.isArray(thumbnails)) {
      const item = thumbnails.find(function (entry) { return Number(entry.channel) === Number(channel); });
      if (item && (item.url || item.image_url)) return item.url || item.image_url;
    } else if (thumbnails && typeof thumbnails === "object") {
      const item = thumbnails[String(channel)] || thumbnails["channel_" + channel];
      if (typeof item === "string") return item;
      if (item && (item.url || item.image_url)) return item.url || item.image_url;
    }
    return mockImageDataUri({ label: "CH " + channel, seed: Number(channel) + String(observation && observation.id || "").length, thumbnail: true });
  }

  async function getObservations() {
    try {
      const response = await fetch(API_BASE + "/observations", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Observation API returned " + response.status);
      const body = await response.json();
      const items = Array.isArray(body) ? body : (body.items || body.observations || []);
      if (!Array.isArray(items)) throw new Error("Unexpected observation response shape");
      return { items: items, mock: false };
    } catch (_error) {
      return { items: cloneDemoObservations(), mock: true };
    }
  }

  async function getObservation(observationId) {
    try {
      const response = await fetch(API_BASE + "/observations/" + encodeURIComponent(observationId), { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Observation API returned " + response.status);
      return { item: await response.json(), mock: false };
    } catch (_error) {
      const item = cloneDemoObservations().find(function (entry) { return entry.id === observationId; });
      return { item: item || cloneDemoObservations()[0], mock: true };
    }
  }

  async function fetchImage(url, options, mockOptions) {
    try {
      const response = await fetch(url, options || {});
      if (!response.ok) throw new Error("Image API returned " + response.status);
      const contentType = (response.headers.get("content-type") || "").toLowerCase();
      if (contentType.includes("application/json")) {
        const body = await response.json();
        const imageUrl = body.image_url || body.url || body.data_uri;
        if (!imageUrl) throw new Error("Image API response did not include image_url");
        return { url: imageUrl, mock: false, objectUrl: false, metadata: body };
      }
      const blob = await response.blob();
      return { url: URL.createObjectURL(blob), mock: false, objectUrl: true, metadata: null };
    } catch (_error) {
      return { url: mockImageDataUri(mockOptions), mock: true, objectUrl: false, metadata: null };
    }
  }

  function channelImageUrl(observationId, channel) {
    return API_BASE + "/observations/" + encodeURIComponent(observationId) + "/channels/" + encodeURIComponent(channel) + "/image";
  }

  function renderImageUrl(observationId) {
    return API_BASE + "/observations/" + encodeURIComponent(observationId) + "/render";
  }

  function observationById(observationId) {
    return cloneDemoObservations().find(function (entry) { return entry.id === observationId; }) || cloneDemoObservations()[0];
  }

  window.ViewLRPT = {
    API_BASE: API_BASE,
    cloneDemoObservations: cloneDemoObservations,
    escapeHtml: escapeHtml,
    formatUtc: formatUtc,
    formatInteger: formatInteger,
    mockImageDataUri: mockImageDataUri,
    thumbnailUrl: thumbnailUrl,
    getObservations: getObservations,
    getObservation: getObservation,
    fetchImage: fetchImage,
    channelImageUrl: channelImageUrl,
    renderImageUrl: renderImageUrl,
    observationById: observationById
  };
}());
