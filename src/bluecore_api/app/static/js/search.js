// For the search results page.
//
// Each results panel (Works & Instances, Other Resources, ...) is wrapped in a
// "[data-panel]" section and paginated. Without JS... pagination results in
// full-page reloads. With JS, this intercepts a panel's "Previous/Next" click,
// fetches associated panel ("&partial=<key>"), and swaps it in place
(function () {
  "use strict";

  function offsetParamFor(key) {
    return key === "single" ? "offset" : key + "_offset";
  }

  // Keep the query ordered so the address bar reads consistently.
  const PARAM_ORDER = ["q", "type", "limit", "offset", "primary_offset", "secondary_offset"];

  function orderParams(url) {
    const rank = function (k) {
      const i = PARAM_ORDER.indexOf(k);
      return i === -1 ? PARAM_ORDER.length : i;
    };
    const entries = Array.from(url.searchParams.entries()).sort(function (a, b) {
      return rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0]);
    });
    const ordered = new URLSearchParams();
    entries.forEach(function (e) {
      ordered.append(e[0], e[1]);
    });
    url.search = ordered.toString();
    return url;
  }

  document.addEventListener("click", function (event) {
    const link = event.target.closest("a.bc-pager-link[href]");
    if (!link) return;

    const section = link.closest("[data-panel]");
    if (!section) return; // not a panel pager => leave it alone

    const key = section.getAttribute("data-panel");
    event.preventDefault();

    const offsetParam = offsetParamFor(key);
    const linkUrl = new URL(link.getAttribute("href"), window.location.href);
    const targetOffset = linkUrl.searchParams.get(offsetParam) || "0";

    // Build the new address from the current page state
    const state = new URL(window.location.href);
    ["q", "type", "limit"].forEach(function (param) {
      if (!state.searchParams.has(param) && linkUrl.searchParams.has(param)) {
        state.searchParams.set(param, linkUrl.searchParams.get(param));
      }
    });
    state.searchParams.set(offsetParam, targetOffset);
    orderParams(state); // stable, grouped param order

    const fetchUrl = new URL(state.href);
    fetchUrl.searchParams.set("partial", key);

    section.setAttribute("aria-busy", "true");
    fetch(fetchUrl.href, { headers: { "X-Requested-With": "fetch" } })
      .then(function (resp) {
        if (!resp.ok) throw new Error("partial fetch failed");
        return resp.text();
      })
      .then(function (html) {
        const tmp = document.createElement("div");
        tmp.innerHTML = html.trim();
        const fresh = tmp.querySelector('[data-panel="' + key + '"]');
        if (!fresh) {
          window.location.assign(state.href); // unexpected shape => fall back
          return;
        }
        section.replaceWith(fresh);
        // Keep the address bar in sync so refresh/share land on this state.
        history.replaceState(null, "", state.href);
      })
      .catch(function () {
        window.location.assign(state.href); // network/server error => fall back
      });
  });
})();
