// For the search results page.
//
// Each results panel (Works & Instances, Other Resources, ...) is wrapped in a
// "[data-panel]" section and paginated. Without JS... pagination results in
// full-page reloads. With JS, this intercepts a panel's "Previous/Next" click,
// fetches associated panel ("&partial=<key>"), and swaps it in place
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    var link = event.target.closest("a.bc-pager-link[href]");
    if (!link) return;

    var section = link.closest("[data-panel]");
    if (!section) return; // not a panel pager =>  leave it alone

    var key = section.getAttribute("data-panel");
    var url = link.getAttribute("href");
    event.preventDefault();

    var sep = url.indexOf("?") === -1 ? "?" : "&";
    var fragmentUrl = url + sep + "partial=" + encodeURIComponent(key);

    section.setAttribute("aria-busy", "true");
    fetch(fragmentUrl, { headers: { "X-Requested-With": "fetch" } })
      .then(function (resp) {
        if (!resp.ok) throw new Error("partial fetch failed");
        return resp.text();
      })
      .then(function (html) {
        var tmp = document.createElement("div");
        tmp.innerHTML = html.trim();
        var fresh = tmp.querySelector('[data-panel="' + key + '"]');
        if (!fresh) {
          window.location.assign(url); // unexpected shape => fall back
          return;
        }
        section.replaceWith(fresh);
        // Keep the address bar in sync so a refresh/share lands on this page.
        history.replaceState(null, "", url);
      })
      .catch(function () {
        window.location.assign(url); // network/server error => fall back
      });
  });
})();
