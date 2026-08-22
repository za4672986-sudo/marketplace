/* ============================================================
   TradeLink Wholesale — app.js
   Premium interaction engine: hero cinema, tilt, magnetic CTAs,
   cart drawer, wishlist AJAX, search overlay, page transitions,
   reveal staggers, micro-interactions.
   Performance: transforms/opacity only, IO + rAF, passive events.
   ============================================================ */
(function () {
  "use strict";

  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var qs = function (s, r) { return (r || document).querySelector(s); };
  var qsa = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- Preloader ---------- */
  var preloader = qs("#preloader");
  function hidePreloader() {
    if (!preloader) return;
    preloader.classList.add("done");
    document.body.classList.add("is-loaded");
    setTimeout(function () { preloader.style.display = "none"; }, 500);
  }
  if (preloader) {
    if (document.readyState === "complete") { setTimeout(hidePreloader, 350); }
    else { window.addEventListener("load", function () { setTimeout(hidePreloader, 350); }); }
    setTimeout(hidePreloader, 2200); // failsafe
  } else {
    document.body.classList.add("is-loaded");
  }

  /* ---------- Scroll progress bar ---------- */
  var prog = qs("#scrollProgress");
  if (prog) {
    var ticking = false;
    function updateProg() {
      var h = document.documentElement;
      var max = h.scrollHeight - h.clientHeight;
      prog.style.transform = "scaleX(" + (max > 0 ? h.scrollTop / max : 0) + ")";
      ticking = false;
    }
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(updateProg); }
    }, { passive: true });
    updateProg();
  }

  /* ---------- Page transitions ---------- */
  if (!REDUCED) {
    document.addEventListener("click", function (e) {
      var a = e.target.closest("a");
      if (!a) return;
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (a.target && a.target !== "_self") return;
      if (a.hasAttribute("download") || a.getAttribute("href") === "#") return;
      var href = a.getAttribute("href") || "";
      if (!href || href.charAt(0) === "#") return;
      var sameOrigin = href.charAt(0) === "/" || href.indexOf(location.origin) === 0;
      if (!sameOrigin) return;
      e.preventDefault();
      document.body.classList.add("page-out");
      setTimeout(function () { window.location.href = href; }, 170);
    }, true);
    document.addEventListener("pageshow", function () { document.body.classList.remove("page-out"); });
  }

  /* ---------- Navbar scroll state (shrink + glass) ---------- */
  var nav = qs(".navbar");
  var navScroll = function () {
    if (!nav) return;
    if (window.scrollY > 24) nav.classList.add("scrolled");
    else nav.classList.remove("scrolled");
  };
  window.addEventListener("scroll", navScroll, { passive: true });
  navScroll();

  /* ---------- Word-by-word text reveal ---------- */
  function splitWords(el) {
    if (REDUCED) return;
    var text = el.textContent;
    var html = "";
    var parts = text.split(/(\s+)/);
    parts.forEach(function (part) {
      if (!part) return;
      if (/^\s+$/.test(part)) { html += part; return; }
      var word = part;
      if (word.indexOf("<") !== -1 || word.indexOf("&") !== -1) { html += word; return; }
      html += "<span class='sw'><span class='sw__in'>" + word + "</span></span> ";
    });
    el.innerHTML = html.trim();
    qsa(".sw", el).forEach(function (w, i) {
      w.style.transitionDelay = (0.25 + i * 0.055) + "s";
    });
    el.classList.add("is-split");
  }
  qsa("[data-split]").forEach(splitWords);

  /* ---------- Mouse-follow light (hero) ---------- */
  var heroLight = qs(".hero__light");
  if (heroLight && !REDUCED && window.matchMedia("(pointer: fine)").matches) {
    var lx = 0, ly = 0, tx = 0, ty = 0, lRun = false;
    document.addEventListener("mousemove", function (e) {
      tx = e.clientX; ty = e.clientY;
      if (!lRun) { lRun = true; requestAnimationFrame(lightLoop); }
    }, { passive: true });
    function lightLoop() {
      lx += (tx - lx) * 0.08; ly += (ty - ly) * 0.08;
      heroLight.style.transform = "translate3d(" + (lx - 60) + "px," + (ly - 60) + "px,0)";
      lRun = false;
      if (Math.abs(tx - lx) > 0.5 || Math.abs(ty - ly) > 0.5) lRun = true;
      if (lRun) requestAnimationFrame(lightLoop);
    }
  }

  /* ---------- 3D tilt (data-tilt) ---------- */
  function initTilt(el) {
    if (REDUCED || !window.matchMedia("(pointer: fine)").matches) return;
    var max = parseFloat(el.getAttribute("data-tilt-max") || "8");
    var glass = qs(".pdp__gallery-glass", el.parentElement) || null;
    var raf = null;
    el.addEventListener("mousemove", function (e) {
      var r = el.getBoundingClientRect();
      var px = (e.clientX - r.left) / r.width - 0.5;
      var py = (e.clientY - r.top) / r.height - 0.5;
      if (raf) return;
      raf = requestAnimationFrame(function () {
        el.style.transform = "perspective(900px) rotateX(" + (-py * max) + "deg) rotateY(" + (px * max) + "deg) translateY(-4px)";
        if (glass) glass.style.opacity = String(0.25 + Math.abs(px) * 0.5 + Math.abs(py) * 0.5);
        raf = null;
      });
    });
    el.addEventListener("mouseleave", function () {
      el.style.transition = "transform .6s cubic-bezier(.2,.8,.2,1)";
      el.style.transform = "perspective(900px) rotateX(0) rotateY(0) translateY(0)";
      if (glass) glass.style.opacity = "0";
      setTimeout(function () { el.style.transition = ""; }, 600);
    });
  }
  qsa("[data-tilt]").forEach(initTilt);

  /* ---------- Magnetic buttons ---------- */
  if (!REDUCED && window.matchMedia("(pointer: fine)").matches) {
    qsa("[data-magnetic]").forEach(function (btn) {
      var strength = 0.28, raf = null;
      btn.addEventListener("mousemove", function (e) {
        var r = btn.getBoundingClientRect();
        var x = (e.clientX - r.left - r.width / 2) * strength;
        var y = (e.clientY - r.top - r.height / 2) * strength;
        if (raf) return;
        raf = requestAnimationFrame(function () {
          btn.style.transform = "translate3d(" + x + "px," + y + "px,0)";
          raf = null;
        });
      });
      btn.addEventListener("mouseleave", function () {
        if (raf) cancelAnimationFrame(raf);
        btn.style.transition = "transform .4s cubic-bezier(.2,.8,.2,1)";
        btn.style.transform = "";
        setTimeout(function () { btn.style.transition = ""; }, 400);
      });
    });
  }

  /* ---------- Reveal system with stagger ---------- */
  var revealIO;
  if ("IntersectionObserver" in window) {
    revealIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add("visible");
          revealIO.unobserve(en.target);
        }
      });
    }, { threshold: 0.1, rootMargin: "0px 0px -40px 0px" });
    qsa(".reveal").forEach(function (el) {
      if (el.classList.contains("visible")) return;
      qsa(":scope > .grid > *, :scope > div > *", el).forEach(function (child, i) {
        child.style.transitionDelay = (i * 60) + "ms";
      });
      revealIO.observe(el);
    });
  }

  /* ---------- Number transition (drawer totals) ---------- */
  function animateValue(el, to, dec) {
    if (!el) return;
    var from = parseFloat((el.dataset.v || el.textContent).replace(/[^0-9.-]/g, "")) || 0;
    var d = dec == null ? 2 : dec;
    var t0 = null, dur = 380;
    el.dataset.v = to;
    function step(ts) {
      if (!t0) t0 = ts;
      var p = Math.min((ts - t0) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = "$" + (from + (to - from) * eased).toFixed(d);
      if (p < 1) requestAnimationFrame(step);
      else el.textContent = "$" + to.toFixed(d);
    }
    requestAnimationFrame(step);
  }

  /* ---------- Cart counter bump ---------- */
  function bumpCount() {
    var b = qs("#cartCount");
    if (!b) return;
    b.classList.remove("bump");
    void b.offsetWidth;
    b.classList.add("bump");
  }
  function setCount(n) {
    var b = qs("#cartCount");
    if (!b) {
      var icon = qs("#cartIconBtn");
      if (!icon) return;
      b = document.createElement("span");
      b.className = "icon-btn__count";
      b.id = "cartCount";
      icon.appendChild(b);
    }
    b.textContent = n;
    bumpCount();
    var sub = qs("#drawerCount");
    if (sub) sub.textContent = n + " item" + (n === 1 ? "" : "s");
  }

  /* ---------- Toast (typed) ---------- */
  function toast(msg, type) {
    var el = qs("#toast");
    if (!el) return;
    var icon = qs(".toast__icon", el);
    var is = qs("#toastMsg", el);
    el.className = "toast show" + (type === "error" ? " toast--error" : type === "success" ? " toast--success" : "");
    if (is) is.textContent = msg;
    if (icon) icon.innerHTML = type === "error"
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M18 6L6 18M6 6l12 12"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6L9 17l-5-5"/></svg>';
    clearTimeout(window._tt);
    window._tt = setTimeout(function () { el.classList.remove("show"); }, 2600);
  }
  window.toast = toast;

  /* ---------- Cart drawer ---------- */
  var drawer = qs("#cartDrawer");
  var drawerOpen = false;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function itemHTML(i) {
    return '<div class="cd-item" data-pid="' + i.id + '">' +
      '<div class="cd-item__img">' + esc(i.name.split(" ").slice(0, 2).join(" ")) + '</div>' +
      '<div class="cd-item__info">' +
      '<a class="cd-item__name" href="/product/' + esc(i.slug) + '">' + esc(i.name) + '</a>' +
      '<div class="cd-item__price">$' + i.unit.toFixed(2) + '/unit' + (i.pct > 0 ? ' <span class="cd-item__save">-' + i.pct + '%</span>' : "") + '</div>' +
      '<div class="cd-item__controls">' +
      '<button type="button" data-cq="-1" aria-label="Decrease quantity">−</button>' +
      '<span class="cd-item__qty">' + i.qty + '</span>' +
      '<button type="button" data-cq="1" aria-label="Increase quantity">+</button>' +
      '</div></div>' +
      '<div class="cd-item__right">' +
      '<div class="cd-item__total">$' + i.line_total.toFixed(2) + '</div>' +
      '<button class="cd-item__remove" type="button" data-cart-remove aria-label="Remove item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/></svg></button>' +
      '</div></div>';
  }
  function emptyHTML() {
    return '<div class="cd-empty"><div class="cd-empty__icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"/></svg></div>' +
      '<h3>Your cart is empty</h3><p>Discover wholesale products to start your order.</p>' +
      '<a class="btn btn-primary" href="/products">Explore Products</a></div>';
  }
  function renderCart(data) {
    var items = qs("#drawerItems");
    if (!items) return;
    items.innerHTML = data.items.length ? data.items.map(itemHTML).join("") : emptyHTML();
    setCount(data.count);
    animateValue(qs("#drawerSubtotal"), data.subtotal);
    var sv = qs("#drawerSavings");
    if (sv) { sv.textContent = "-$" + data.savings.toFixed(2); sv.style.display = data.savings > 0 ? "" : "none"; }
    animateValue(qs("#drawerTotal"), data.total);
    qsa(".cd-item", items).forEach(function (it, i) {
      it.style.transitionDelay = (i * 45) + "ms";
      it.classList.add("in");
    });
  }
  function fetchCart() {
    return fetch("/api/cart/summary").then(function (r) {
      if (!r.ok) throw new Error("auth");
      return r.json();
    });
  }
  function openDrawer() {
    if (!drawer) return;
    drawerOpen = true;
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    document.body.classList.add("no-scroll");
    qs("#drawerItems") && qsa(".cd-item", qs("#drawerItems")).forEach(function (it, i) {
      it.style.transitionDelay = (i * 45) + "ms";
      it.classList.add("in");
    });
  }
  function closeDrawer() {
    if (!drawer) return;
    drawerOpen = false;
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("no-scroll");
  }
  function toggleCart() {
    if (drawerOpen) closeDrawer(); else openDrawer();
  }
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-cart-open]");
    if (opener) {
      e.preventDefault();
      if (drawer) { toggleCart(); }
      else { window.location.href = opener.getAttribute("href"); }
      return;
    }
    if (e.target.closest("[data-cart-close]") || e.target.closest(".cart-drawer__overlay")) {
      closeDrawer();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && drawerOpen) closeDrawer();
  });

  /* Drawer qty +/- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-cq]");
    if (!btn) return;
    var item = btn.closest(".cd-item");
    if (!item) return;
    var qtyEl = qs(".cd-item__qty", item);
    var pid = item.getAttribute("data-pid");
    var qty = parseInt(qtyEl.textContent, 10) + parseInt(btn.getAttribute("data-cq"), 10);
    if (qty < 1) return;
    qtyEl.textContent = qty;
    qtyEl.classList.remove("tick"); void qtyEl.offsetWidth; qtyEl.classList.add("tick");
    fetch("/cart/update", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "product_id=" + pid + "&qty=" + qty,
      credentials: "same-origin"
    }).then(function (r) { return r.ok ? fetchCart() : Promise.reject(); })
      .then(renderCart).catch(function () { toast("Please sign in", "error"); });
  });

  /* Drawer remove */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-cart-remove]");
    if (!btn) return;
    var item = btn.closest(".cd-item");
    if (!item) return;
    var pid = item.getAttribute("data-pid");
    item.classList.add("out");
    setTimeout(function () {
      fetch("/cart/remove", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "product_id=" + pid,
        credentials: "same-origin"
      }).then(function (r) { return r.ok ? fetchCart() : Promise.reject(); })
        .then(renderCart).catch(function () { toast("Please sign in", "error"); });
    }, 220);
  });

  /* ---------- Add-to-cart AJAX interception ---------- */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form || !form.matches('form[action*="/cart/add"]')) return;
    e.preventDefault();
    var fd = new FormData(form);
    var btn = qs("button[type=submit]", form);
    var orig = btn ? btn.innerHTML : "";
    if (btn) {
      btn.classList.add("is-loading");
      btn.innerHTML = '<span class="spinner"></span> Adding…';
    }
    fetch("/cart/add", { method: "POST", body: fd, credentials: "same-origin" })
      .then(function (r) {
        return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || "Error"); return d; });
      })
      .then(function (d) {
        setCount(d.count);
        toast(d.msg, "success");
        if (drawer && d.count) {
          fetchCart().then(function (data) {
            if (drawerOpen) renderCart(data);
            else openDrawer();
          }).catch(function () {});
        }
      })
      .catch(function (err) {
        toast(err.message || "Could not add to cart", "error");
      })
      .then(function () {
        if (btn) { btn.classList.remove("is-loading"); btn.innerHTML = orig; }
      });
  });

  /* ---------- Buy Now ---------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-buy-now]");
    if (!btn) return;
    var pid = btn.getAttribute("data-pid");
    var moq = parseInt(btn.getAttribute("data-moq"), 10) || 1;
    var qty = parseInt((qs("#qtyInput") || {}).value, 10) || moq;
    btn.classList.add("is-loading");
    fetch("/cart/add", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "product_id=" + pid + "&qty=" + qty,
      credentials: "same-origin"
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) throw new Error(d.error);
      setCount(d.count);
      window.location.href = "/checkout";
    }).catch(function (err) {
      btn.classList.remove("is-loading");
      if ((err.message || "").indexOf("sign in") > -1 || (err.message || "").indexOf("Please") > -1) {
        toast("Please sign in to checkout", "error");
        window.location.href = "/login?next=" + encodeURIComponent(location.pathname);
      } else { toast(err.message || "Error", "error"); }
    });
  });

  /* ---------- Wishlist AJAX ---------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-wish]");
    if (!btn) return;
    e.preventDefault();
    var pid = btn.getAttribute("data-pid");
    fetch("/wishlist/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "product_id=" + pid,
      credentials: "same-origin"
    }).then(function (r) {
      if (!r.ok && (r.status === 302 || r.status === 401)) {
        toast("Sign in to save favorites", "error");
        setTimeout(function () { window.location.href = "/login?next=" + encodeURIComponent(location.pathname); }, 900);
        throw new Error("auth");
      }
      if (!r.ok) throw new Error("error");
      return r;
    }).then(function () {
      var on = btn.classList.toggle("active");
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.classList.remove("pop"); void btn.offsetWidth; btn.classList.add("pop");
      toast(on ? "Saved to wishlist" : "Removed from wishlist", "success");
    }).catch(function (e2) { if (e2 && e2.message !== "auth") toast("Could not update wishlist", "error"); });
  });

  /* ---------- Mobile search overlay ---------- */
  var searchOverlay = qs("#searchOverlay");
  var overlayInput = qs("#overlaySearchInput");
  function openSearch() {
    if (!searchOverlay) return;
    searchOverlay.classList.add("open");
    searchOverlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("no-scroll");
    setTimeout(function () { overlayInput && overlayInput.focus(); }, 250);
  }
  function closeSearch() {
    if (!searchOverlay) return;
    searchOverlay.classList.remove("open");
    searchOverlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("no-scroll");
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-search-open]")) { e.preventDefault(); openSearch(); return; }
    if (e.target.closest("[data-search-close]")) closeSearch();
  });
  if (searchOverlay && overlayInput) {
    overlayInput.addEventListener("input", function () {
      var q = overlayInput.value.trim();
      var res = qs("#overlayResults");
      if (q.length < 2) { res.innerHTML = ""; return; }
      fetch("/api/search?q=" + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (d) {
        if (!d.results || !d.results.length) {
          res.innerHTML = '<div class="search-overlay__empty">No matches for “' + esc(q) + '” — try a different term.</div>';
          return;
        }
        res.innerHTML = d.results.map(function (p) {
          return '<a class="search-overlay__result" href="/product/' + esc(p.slug) + '">' +
            '<div class="search-overlay__thumb"></div>' +
            '<div><div class="search-overlay__rname">' + esc(p.name) + '</div>' +
            '<div class="search-overlay__rprice">$' + Number(p.price).toFixed(2) + '/unit · MOQ ' + p.moq + '</div></div>' +
            '<span class="search-overlay__go-arrow">→</span></a>';
        }).join("");
      });
    });
    overlayInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        var q = overlayInput.value.trim();
        if (q) window.location.href = "/products?q=" + encodeURIComponent(q);
      }
    });
  }

  /* ---------- Copy to clipboard ---------- */
  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-copy]");
    if (!el) return;
    var text = el.getAttribute("data-copy");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        toast("Copied to clipboard", "success");
      }, function () { toast("Copy failed", "error"); });
    }
  });

  /* ---------- Form validation shake ---------- */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form || !form.checkValidity) return;
    if (!form.checkValidity()) {
      qsa("input,select,textarea", form).forEach(function (f) {
        if (!f.checkValidity()) {
          f.classList.add("invalid");
          f.addEventListener("input", function h() { f.classList.remove("invalid"); f.removeEventListener("input", h); }, { once: true });
        }
      });
    }
  }, true);

  /* ---------- Accessibility: skip heavy init when reduced motion ---------- */
  if (REDUCED) {
    qsa(".reveal").forEach(function (el) { el.classList.add("visible"); });
  }
})();