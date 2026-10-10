(function () {
  "use strict";

  const API_BASE = "/api";

  function formatUtc(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value || "—");
    return date.toISOString().slice(0, 19).replace("T", " ");
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

  async function getObservations() {
    const response = await fetch(API_BASE + "/observations", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("Observation API returned " + response.status);
    const body = await response.json();
    const items = Array.isArray(body) ? body : (body.items || []);
    if (!Array.isArray(items)) throw new Error("Unexpected observation response shape");
    return { items: items };
  }

  async function getObservation(observationId) {
    const response = await fetch(API_BASE + "/observations/" + encodeURIComponent(observationId), { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("Observation API returned " + response.status);
    const body = await response.json();
    return body.item || body;
  }

  function renderImageUrl(observationId) {
    return API_BASE + "/observations/" + encodeURIComponent(observationId) + "/render";
  }

  window.ViewLRPT = {
    API_BASE: API_BASE,
    escapeHtml: escapeHtml,
    formatUtc: formatUtc,
    formatInteger: formatInteger,
    getObservations: getObservations,
    getObservation: getObservation,
    renderImageUrl: renderImageUrl
  };
}());