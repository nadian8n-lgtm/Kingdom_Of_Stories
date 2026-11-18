"use strict";
/* لوحة تحكم مملكة الأسرار — مدونة شخصية تعمل كاملة في المتصفح مع GitHub API، بلا سيرفر وبلا قاعدة بيانات.
   لا تُحمّل أي سكربت خارجي (ولا إعلانات) حتى لا يصل المفتاح المحفوظ في المتصفح إلى طرف ثالث. */
(function () {
  const CATS = [
    ["story_realistic", "واقعي وإنساني"],
    ["story_mystery", "غموض وإثارة"],
    ["story_scifi", "خيال علمي وتكنولوجيا"],
    ["story_fantasy", "فانتازيا ومغامرات"],
    ["story_horror", "رعب نفسي"],
    ["story_history", "تاريخي وثقافي"],
    ["story_comedy", "كوميديا وسخرية"],
    ["kids_3_6", "براعم الصغار (3-6 سنوات)"],
    ["kids_7_10", "مغامرو المستقبل (7-10 سنوات)"],
    ["kids_11_14", "يافعون ومراهقون (11-14 سنة)"],
    ["ar_tech", "تقنية (قراءة رأي)"],
    ["ar_arts", "فن وثقافة (قراءة رأي)"],
    ["ar_books", "المكتبة الرقمية المجانية"]
  ];
  const CATNAME = {};
  CATS.forEach(function (c) { CATNAME[c[0]] = c[1]; });

  const STORY_CATS = {
    story_realistic: 1, story_mystery: 1, story_scifi: 1, story_fantasy: 1,
    story_horror: 1, story_history: 1, story_comedy: 1,
    kids_3_6: 1, kids_7_10: 1, kids_11_14: 1
  };
  const KID_CATS = { kids_3_6: 1, kids_7_10: 1, kids_11_14: 1 };
  const SOURCE_CATS = { ar_books: 1, ar_tech: 1, ar_arts: 1 };
  const TAG_FIELDS = [
    ["short", "#tagShort"], ["flash", "#tagFlash"],
    ["serial", "#tagSerial"], ["interactive", "#tagInteractive"]
  ];
  function isStoryCat(cat) { return !!STORY_CATS[cat]; }
  function isKidCat(cat) { return !!KID_CATS[cat]; }
  function needsSources(cat) { return !!SOURCE_CATS[cat]; }
  function minWords(cat) { return cat === "ar_books" ? 430 : (SOURCE_CATS[cat] || KID_CATS[cat] ? 800 : 2000); }
  function maxWords(cat) { return cat === "ar_books" ? 820 : (SOURCE_CATS[cat] || KID_CATS[cat] ? 1500 : 5000); }
  function wordHint(cat) {
    return "الطول المستحسن لهذا القسم: " + minWords(cat) + "–" + maxWords(cat) +
      " كلمة" + (cat === "ar_books" ? " (مقالات المكتبة كما كانت)." : " — التنبيه فقط، ويمكن حفظ مسودة.");
  }

  const CFG_KEY = "np_admin_cfg", PAT_KEY = "np_admin_pat", PIN_KEY = "np_admin_pin";
  const $ = function (s) { return document.querySelector(s); };

  const S = {
    cfg: { repo: "", branch: "main", workflow: "rebuild.yml" },
    pat: "", pin: "", data: null, sha: "", cat: "story_realistic",
    ops: [], dirty: false, busy: false,
    editing: null, editImage: "", pendingFile: null, editSources: []
  };

  // ---------------------------------------------------------------- helpers
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function lsDel(k) { try { localStorage.removeItem(k); } catch (e) {} }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function h(tag, props) {
    const n = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        const v = props[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "class") n.className = v;
        else if (k === "text") n.textContent = v;
        else if (k.indexOf("on") === 0 && typeof v === "function") n.addEventListener(k.slice(2), v);
        else n.setAttribute(k, v);
      });
    }
    for (let i = 2; i < arguments.length; i++) {
      const kid = arguments[i];
      if (kid === null || kid === undefined) continue;
      n.append(kid && kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return n;
  }
  function words(t) { return String(t || "").trim().split(/\s+/).filter(Boolean).length; }
  function arabicRatio(t) {
    const letters = String(t || "").match(/\p{L}/gu) || [];
    if (!letters.length) return 0;
    return (String(t).match(/[\u0621-\u064A]/g) || []).length / letters.length;
  }
  function pad(n) { return String(n).padStart(2, "0"); }
  function isoUTC(d) {
    return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()) + "T" +
      pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + "+00:00";
  }
  function toLocalInput(iso) {
    const d = new Date(iso || Date.now());
    if (isNaN(d)) return "";
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function fromLocalInput(v) {
    const d = new Date(v);
    return isNaN(d) ? isoUTC(new Date()) : isoUTC(d);
  }
  function newId(cat) {
    const d = new Date();
    const stamp = d.getUTCFullYear() + pad(d.getUTCMonth() + 1) + pad(d.getUTCDate()) + pad(d.getUTCHours()) + pad(d.getUTCMinutes());
    return cat + "-" + stamp + "-" + Math.random().toString(16).slice(2, 8);
  }
  function b64e(s) {
    const bytes = new TextEncoder().encode(s);
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(bin);
  }
  function b64d(s) {
    const bin = atob(String(s || "").replace(/\s/g, ""));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }
  async function sha256(s) {
    s = String(s);
    try {
      const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
      return Array.prototype.map.call(new Uint8Array(buf), function (b) { return b.toString(16).padStart(2, "0"); }).join("");
    } catch (e) {
      let x = 5381;
      for (let i = 0; i < s.length; i++) x = ((x << 5) + x + s.charCodeAt(i)) >>> 0;
      return "x" + x.toString(16);
    }
  }
  function toast(msg, kind) {
    const t = h("div", { class: "toast" + (kind ? " " + kind : ""), text: msg });
    $("#toasts").append(t);
    setTimeout(function () { t.remove(); }, kind === "bad" ? 9000 : 5200);
  }
  function setStatus(text, kind) {
    const el = $("#stat");
    el.textContent = text;
    el.className = "chip" + (kind ? " " + kind : "");
  }
  function setBusy(on, msg) {
    S.busy = !!on;
    document.querySelectorAll("#bar .btn").forEach(function (b) { b.disabled = !!on; });
    if (!on) updateSaveBtn();
    if (msg) setStatus(msg, on ? "warn" : "ok");
  }
  function updateSaveBtn() {
    const b = $("#bSave");
    b.disabled = !!S.busy || !S.dirty || !S.ops.length;
    $("#dirty").classList.toggle("hidden", !S.dirty);
  }
  function mark() { S.dirty = true; updateSaveBtn(); }

  // ---------------------------------------------------------------- GitHub API
  async function gh(method, path, body) {
    if (!S.cfg.repo || !S.pat) throw new Error("أضف المستودع والمفتاح في الإعدادات أولاً");
    const res = await fetch("https://api.github.com/repos/" + S.cfg.repo + path, {
      method: method,
      headers: Object.assign({
        "Authorization": "Bearer " + S.pat,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
      }, body ? { "Content-Type": "application/json" } : {}),
      body: body ? JSON.stringify(body) : undefined
    });
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) {}
    if (!res.ok) {
      const err = new Error((data && data.message) || text.slice(0, 220) || ("HTTP " + res.status));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function normalizeDoc(doc) {
    if (!doc || typeof doc !== "object") doc = {};
    if (!doc.articles || typeof doc.articles !== "object") doc.articles = {};
    CATS.forEach(function (c) { if (!Array.isArray(doc.articles[c[0]])) doc.articles[c[0]] = []; });
    return doc;
  }

  async function fetchDoc() {
    const r = await gh("GET", "/contents/articles.json?ref=" + encodeURIComponent(S.cfg.branch));
    return { doc: normalizeDoc(JSON.parse(b64d(r.content))), sha: r.sha };
  }

  async function loadDoc() {
    const r = await fetchDoc();
    S.data = r.doc;
    S.sha = r.sha;
    S.ops = [];
    S.dirty = false;
    if (!S.data.articles[S.cat]) S.cat = CATS[0][0];
    updateSaveBtn();
  }

  async function putFile(path, b64, message) {
    let sha = null;
    try {
      const ex = await gh("GET", "/contents/" + path + "?ref=" + encodeURIComponent(S.cfg.branch));
      sha = ex.sha;
    } catch (e) { /* الملف جديد */ }
    const body = { message: message, content: b64, branch: S.cfg.branch };
    if (sha) body.sha = sha;
    return gh("PUT", "/contents/" + path, body);
  }

  async function rebuild() {
    try {
      await gh("POST", "/actions/workflows/" + encodeURIComponent(S.cfg.workflow) + "/dispatches", { ref: S.cfg.branch });
      toast("تم إرسال طلب إعادة بناء الموقع — الصفحات ستتحدّث خلال 1–3 دقائق.", "ok");
      return true;
    } catch (e) {
      toast("حُفظت التعديلات، لكن تعذّر تشغيل «مملكة الأسرار — إعادة البناء»: " + e.message +
        " — شغّله يدوياً من تبويب Actions، أو انتظر النشر التلقائي.", "warn");
      return false;
    }
  }

  function handleErr(e) {
    const status = e && e.status;
    if (status === 401) toast("المفتاح غير صالح أو منتهي الصلاحية. افتح ⚙ وأدخل مفتاحاً جديداً.", "bad");
    else if (status === 403) toast("رفض GitHub الطلب: تحقّق من صلاحيتي Contents و Actions، أو من حد الطلبات.", "bad");
    else if (status === 404) toast("لم يُعثر على المستودع أو على articles.json. تحقّق من owner/repo والفرع.", "bad");
    else toast((e && e.message) || String(e), "bad");
    setStatus("خطأ", "bad");
    setBusy(false);
  }

  // ---------------------------------------------------------------- operations log (تعمل كـ patch يُعاد تطبيقه، فلا يحدث تعارض مع البوت)
  function applyOps(doc, ops) {
    ops.forEach(function (op) {
      const A = doc.articles;
      if (op.t === "add") {
        (A[op.cat] = A[op.cat] || []).unshift(clone(op.a));
      } else if (op.t === "update") {
        const from = op.fromCat || op.cat;
        const arr = A[from] || [];
        const i = arr.findIndex(function (a) { return a.id === op.id; });
        if (i >= 0) {
          if (from === op.cat) arr[i] = clone(op.a);
          else { arr.splice(i, 1); (A[op.cat] = A[op.cat] || []).unshift(clone(op.a)); }
        } else {
          (A[op.cat] = A[op.cat] || []).unshift(clone(op.a));
        }
      } else if (op.t === "delete") {
        Object.keys(A).forEach(function (k) { A[k] = A[k].filter(function (a) { return a.id !== op.id; }); });
      } else if (op.t === "order") {
        const cur = A[op.cat] || [];
        const byId = {};
        cur.forEach(function (a) { byId[a.id] = a; });
        const out = [];
        op.ids.forEach(function (id) { if (byId[id]) { out.push(byId[id]); delete byId[id]; } });
        cur.forEach(function (a) { if (byId[a.id]) out.push(a); });
        A[op.cat] = out;
      }
    });
    return doc;
  }

  function snapshotOrder(cat) {
    const items = S.data.articles[cat] || [];
    S.ops = S.ops.filter(function (o) { return !(o.t === "order" && o.cat === cat); });
    S.ops.push({ t: "order", cat: cat, ids: items.map(function (a) { return a.id; }) });
  }

  function locate(id) {
    const A = S.data.articles;
    for (let i = 0; i < CATS.length; i++) {
      const cat = CATS[i][0];
      const idx = (A[cat] || []).findIndex(function (a) { return a.id === id; });
      if (idx >= 0) return { cat: cat, i: idx, a: A[cat][idx] };
    }
    return null;
  }

  function pushUpdate(cat, a, fromCat) {
    S.ops.push({ t: "update", id: a.id, cat: cat || fromCat, fromCat: fromCat || cat, a: clone(a) });
  }

  // ---------------------------------------------------------------- rendering
  function renderAll() { renderSide(); renderList(); updateSaveBtn(); }

  function renderSide() {
    const side = $("#side");
    side.innerHTML = "";
    CATS.forEach(function (c) {
      const n = S.data && S.data.articles[c[0]] ? S.data.articles[c[0]].length : 0;
      side.append(h("button", {
        class: "cat" + (c[0] === S.cat ? " active" : ""),
        onclick: function () { S.cat = c[0]; renderAll(); }
      }, h("span", { class: "cn", text: c[1] }), h("span", { class: "cc", text: String(n) })));
    });
    side.append(h("div", { class: "side-note", text: "الترتيب هنا هو ترتيب الظهور داخل القسم: قصة يدوية جديدة في الأعلى، والباقي حسب الأحدث. المصادر مطلوبة في قراءات نكسوس والمكتبة فقط." }));
  }

  function badges(a, cat) {
    const out = [];
    out.push(h("span", { class: "badge" + (a.manual ? " manual" : ""), text: a.manual ? "يدوي" : "آلي" }));
    const wc = words(a.content);
    if (needsSources(cat) && !(a.sources && a.sources.length)) out.push(h("span", { class: "badge bad", text: "بلا مصدر" }));
    if (!a.image) out.push(h("span", { class: "badge warn", text: "بلا صورة" }));
    if (wc < minWords(cat)) out.push(h("span", { class: "badge warn", text: wc + " كلمة" }));
    else if (wc > maxWords(cat)) out.push(h("span", { class: "badge warn", text: wc + " كلمة" }));
    return out;
  }

  function renderList() {
    const list = $("#list");
    list.innerHTML = "";
    $("#hCat").textContent = CATNAME[S.cat] || S.cat;
    const items = (S.data && S.data.articles[S.cat]) || [];
    const q = ($("#q").value || "").trim();
    const shown = items.map(function (a, i) { return { a: a, i: i }; })
      .filter(function (x) { return !q || String(x.a.title || "").indexOf(q) >= 0; });
    if (!shown.length) {
      list.append(h("div", { class: "empty", text: items.length ? "لا نتيجة للبحث." : "لا يوجد مقال في هذا القسم بعد." }));
      return;
    }
    shown.forEach(function (x) { list.append(row(x.a, x.i, items.length)); });
  }

  function row(a, i, total) {
    const thumb = h("div", { class: "thumb" },
      a.image ? h("img", { src: "../" + a.image, alt: "", loading: "lazy", onerror: function (e) { e.target.style.display = "none"; } }) : "بلا صورة");
    const sub = h("div", { class: "sub" },
      h("span", { text: String(a.date || "").slice(0, 10) }),
      h("span", { text: words(a.content) + " كلمة" }));
    badges(a, S.cat).forEach(function (b) { sub.append(b); });
    const acts = h("div", { class: "acts" },
      h("button", { title: "أعلى", disabled: i === 0, onclick: function () { moveBy(a.id, -1); } }, "↑"),
      h("button", { title: "أسفل", disabled: i === total - 1, onclick: function () { moveBy(a.id, 1); } }, "↓"),
      h("button", { title: "نقل إلى قسم آخر", onclick: function () { openMover(a.id); } }, "📁"),
      h("button", { title: "تعديل", onclick: function () { openEditor(a.id); } }, "✏️"),
      h("button", { title: "حذف", onclick: function () { removeArticle(a.id); } }, "🗑"),
      h("a", { href: "../articles/" + a.id + ".html", target: "_blank", rel: "noopener", title: "معاينة الصفحة" }, "👁"));
    return h("div", { class: "art" },
      h("div", { class: "ord", text: String(i + 1) }),
      thumb,
      h("div", { class: "meta" },
        h("div", { class: "t", text: a.title, title: a.title, onclick: function () { openEditor(a.id); } }),
        sub),
      acts);
  }

  // ---------------------------------------------------------------- mutations
  function moveBy(id, delta) {
    const f = locate(id);
    if (!f) return;
    const arr = S.data.articles[f.cat];
    const j = f.i + delta;
    if (j < 0 || j >= arr.length) return;
    const tmp = arr[f.i];
    arr[f.i] = arr[j];
    arr[j] = tmp;
    [arr[f.i], arr[j]].forEach(function (x) { x.manual = true; x.cat_ok = true; });
    pushUpdate(f.cat, arr[f.i], f.cat);
    pushUpdate(f.cat, arr[j], f.cat);
    snapshotOrder(f.cat);
    mark();
    renderList();
  }

  function removeArticle(id) {
    const f = locate(id);
    if (!f) return;
    if (!confirm("حذف هذا المقال نهائياً من الموقع؟\n\n" + f.a.title)) return;
    S.data.articles[f.cat].splice(f.i, 1);
    S.ops.push({ t: "delete", id: id });
    snapshotOrder(f.cat);
    mark();
    renderAll();
    toast("حُذف من القائمة — اضغط «حفظ ونشر» لتنفيذ الحذف على الموقع.", "warn");
  }

  function openMover(id) {
    const box = $("#moveCats");
    box.innerHTML = "";
    CATS.forEach(function (c) {
      box.append(h("button", {
        class: "btn ghost", onclick: function () { $("#mover").classList.add("hidden"); moveTo(id, c[0]); }
      }, c[1]));
    });
    $("#mover").classList.remove("hidden");
  }

  function moveTo(id, target) {
    const f = locate(id);
    if (!f) return;
    if (f.cat === target) { toast("المقال موجود في هذا القسم أصلاً.", "warn"); return; }
    const a = f.a;
    // القسم الجديد له شروط (عدد الكلمات، المصادر…): نتحقق قبل النقل حتى لا يفشل البناء
    const res = validate({
      title: a.title || "", summary: a.summary || "", cat: target, date: a.date,
      body: a.content || "",
      sources: (a.sources || []).map(function (s) { return { publisher: (s && s.publisher) || "", url: (s && s.url) || "" }; }),
      tags: Array.isArray(a.tags) ? a.tags : [], warning: a.warning || "",
      manual: true, credit: (a.image_credit && (a.image_credit.author || a.image_credit.source)) || "نكسوس",
      auto: !a.image
    });
    if (res.errors.length) {
      openEditor(id, target);
      formErr(res.errors.concat("عدّل ما هو مطلوب أعلاه ثم اضغط «حفظ التغييرات» لينتقل المقال إلى «" + CATNAME[target] + "»."));
      return;
    }
    S.data.articles[f.cat].splice(f.i, 1);
    a.manual = true;
    a.cat_ok = true;
    S.data.articles[target].unshift(a);
    S.ops.push({ t: "update", id: a.id, cat: target, fromCat: f.cat, a: clone(a) });
    snapshotOrder(f.cat);
    snapshotOrder(target);
    mark();
    S.cat = target;
    renderAll();
    toast("نُقل إلى «" + CATNAME[target] + "» — اضغط «حفظ ونشر».", "warn");
  }

  // ---------------------------------------------------------------- save (patch replay = no conflict with the bot)
  async function commit() {
    if (S.busy) return;
    if (!S.ops.length) { toast("لا توجد تعديلات جديدة.", "warn"); return; }
    if (!confirm("رفع التعديلات إلى GitHub ونشرها على الموقع الآن؟")) return;
    setBusy(true, "جارٍ الرفع…");
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        const fresh = await fetchDoc();
        const doc = applyOps(fresh.doc, S.ops);
        const body = JSON.stringify({
          categories: doc.categories || (S.data && S.data.categories) || null,
          articles: doc.articles
        }, null, 1);
        await gh("PUT", "/contents/articles.json", {
          message: "تحرير في مملكة الأسرار: " + S.ops.length + " تغيير",
          content: b64e(body),
          sha: fresh.sha,
          branch: S.cfg.branch
        });
        S.data = doc;
        S.sha = "";
        S.ops = [];
        S.dirty = false;
        renderAll();
        setStatus("محفوظ", "ok");
        toast("تم رفع التعديلات إلى GitHub.", "ok");
        S.busy = false;
        updateSaveBtn();
        await rebuild();
        return;
      } catch (e) {
        if (e.status === 409 && attempt < 3) {
          toast("تغيّر الملف من طرف النشر التلقائي — إعادة المحاولة " + attempt + "/3…", "warn");
          continue;
        }
        handleErr(e);
        return;
      }
    }
    setBusy(false);
  }

  // ---------------------------------------------------------------- gate
  function showSetup(prefillPat) {
    $("#gate").classList.remove("hidden");
    $("#lockForm").classList.add("hidden");
    $("#setupForm").classList.remove("hidden");
    $("#sRepo").value = S.cfg.repo || "";
    $("#sBranch").value = S.cfg.branch || "main";
    $("#sPat").value = prefillPat ? (S.pat || "") : "";
    $("#sPin").value = "";
    $("#sPin2").value = "";
    $("#setupErr").classList.add("hidden");
    setTimeout(function () { ($("#sRepo").value ? $("#sPin") : $("#sRepo")).focus(); }, 60);
  }
  function showLock() {
    $("#gate").classList.remove("hidden");
    $("#setupForm").classList.add("hidden");
    $("#lockForm").classList.remove("hidden");
    $("#lockWho").textContent = S.cfg.repo + " · " + S.cfg.branch;
    $("#lPin").value = "";
    $("#lockErr").classList.add("hidden");
    setTimeout(function () { $("#lPin").focus(); }, 60);
  }
  function showErr(sel, msg) { const e = $(sel); e.textContent = msg; e.classList.remove("hidden"); }

  async function setupSubmit(ev) {
    ev.preventDefault();
    const repo = $("#sRepo").value.trim().replace(/^https?:\/\/github\.com\//i, "").replace(/\/+$/, "");
    const branch = $("#sBranch").value.trim() || "main";
    const pat = $("#sPat").value.trim();
    const pin = $("#sPin").value.trim();
    const pin2 = $("#sPin2").value.trim();
    if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) return showErr("#setupErr", "صيغة المستودع: owner/repo — مثال: owner/nexus-blog");
    if (pat.length < 20) return showErr("#setupErr", "المفتاح قصير جداً — انسخه كاملاً من GitHub.");
    if (!/^\d{4,12}$/.test(pin)) return showErr("#setupErr", "رمز الدخول من 4 إلى 12 رقماً.");
    if (pin !== pin2) return showErr("#setupErr", "الرمزان غير متطابقين.");
    const btn = $("#setupForm button[type=submit]");
    const oldRepo = S.cfg.repo, oldPat = S.pat;
    btn.disabled = true; btn.textContent = "جارٍ التحقق…";
    S.cfg.repo = repo; S.cfg.branch = branch; S.pat = pat;
    try {
      await gh("GET", "");
      await loadDoc();
      S.pin = await sha256(pin);
      lsSet(CFG_KEY, JSON.stringify(S.cfg));
      lsSet(PAT_KEY, S.pat);
      lsSet(PIN_KEY, S.pin);
      enterPanel();
      toast("تم الاتصال بالمستودع. أنت الآن في لوحة التحكم.", "ok");
    } catch (e) {
      S.cfg.repo = oldRepo; S.pat = oldPat;
      showErr("#setupErr", "تعذّر الاتصال: " + e.message + " — تحقّق من اسم المستودع وصلاحيات المفتاح.");
    } finally {
      btn.disabled = false; btn.textContent = "حفظ والاتصال";
    }
  }

  async function lockSubmit(ev) {
    ev.preventDefault();
    const hash = await sha256($("#lPin").value.trim());
    if (hash !== S.pin) { showErr("#lockErr", "رمز غير صحيح."); $("#lPin").value = ""; return; }
    S.pat = lsGet(PAT_KEY) || "";
    if (!S.pat) { showErr("#lockErr", "المفتاح غير محفوظ في هذا المتصفح — أعد الإعداد."); showSetup(true); return; }
    setStatus("جارٍ التحميل…", "warn");
    try { await loadDoc(); enterPanel(); }
    catch (e) { showErr("#lockErr", "تعذّر تحميل المقالات: " + e.message); }
  }

  function enterPanel() {
    $("#gate").classList.add("hidden");
    $("#bar").classList.remove("hidden");
    $("#panel").classList.remove("hidden");
    setStatus("متصل", "ok");
    renderAll();
  }

  function lockPanel() {
    if (S.dirty && !confirm("لديك تعديلات غير محفوظة ستُفقد عند القفل. متابعة؟")) return;
    S.data = null; S.ops = []; S.dirty = false; S.pat = "";
    $("#bar").classList.add("hidden");
    $("#panel").classList.add("hidden");
    showLock();
  }

  function openSettings() {
    $("#gRepo").value = S.cfg.repo;
    $("#gBranch").value = S.cfg.branch;
    $("#gWorkflow").value = S.cfg.workflow;
    $("#gPat").value = "";
    $("#gPin").value = "";
    $("#setErr").classList.add("hidden");
    $("#settings").classList.remove("hidden");
  }

  async function saveSettings() {
    const repo = $("#gRepo").value.trim();
    const branch = $("#gBranch").value.trim() || "main";
    const wf = $("#gWorkflow").value.trim() || "rebuild.yml";
    const pat = $("#gPat").value.trim();
    const pin = $("#gPin").value.trim();
    if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) return showErr("#setErr", "صيغة المستودع غير صحيحة.");
    if (pin && !/^\d{4,12}$/.test(pin)) return showErr("#setErr", "الرمز من 4 إلى 12 رقماً.");
    S.cfg = { repo: repo, branch: branch, workflow: wf };
    if (pat) S.pat = pat;
    if (pin) S.pin = await sha256(pin);
    lsSet(CFG_KEY, JSON.stringify(S.cfg));
    lsSet(PAT_KEY, S.pat);
    if (pin) lsSet(PIN_KEY, S.pin);
    $("#settings").classList.add("hidden");
    toast("حُفظت الإعدادات في هذا المتصفح.", "ok");
    setStatus("جارٍ التحديث…", "warn");
    try { await loadDoc(); renderAll(); setStatus("متصل", "ok"); }
    catch (e) { handleErr(e); }
  }

  function backup() {
    if (!S.data) return;
    const blob = new Blob([JSON.stringify({ categories: S.data.categories, articles: S.data.articles }, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "articles-backup-" + new Date().toISOString().slice(0, 10) + ".json";
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 3000);
    toast("نُزّلت نسخة احتياطية من الملف الحالي.", "ok");
  }

  function wipe() {
    if (!confirm("مسح المستودع والمفتاح والرمز من هذا المتصفح؟ ستحتاج إلى إعداد جديد كاملاً.")) return;
    lsDel(CFG_KEY); lsDel(PAT_KEY); lsDel(PIN_KEY);
    location.reload();
  }

  // ---------------------------------------------------------------- editor
  function fillSelects() {
    const fc = $("#fCat");
    if (!fc.options.length) CATS.forEach(function (c) { fc.append(h("option", { value: c[0] }, c[1])); });
  }

  function setPreview(rel) {
    const box = $("#fPrev");
    box.innerHTML = "";
    if (rel) box.append(h("img", { src: "../" + rel, alt: "" }));
    else box.append(document.createTextNode(S.pendingFile ? "صورة جديدة" : "لا صورة"));
  }

  function clearFormMsgs() {
    ["#edErrs", "#edWarns"].forEach(function (s) {
      const e = $(s); e.classList.add("hidden"); e.innerHTML = "";
    });
  }
  function formErr(list) {
    const e = $("#edErrs");
    e.innerHTML = "";
    e.append(h("div", { text: "لا يمكن الحفظ:" }));
    const ul = h("ul");
    list.forEach(function (x) { ul.append(h("li", { text: x })); });
    e.append(ul);
    e.classList.remove("hidden");
    e.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function formWarn(list) {
    const e = $("#edWarns");
    e.innerHTML = "";
    e.append(h("div", { text: "تنبيهات (لا تمنع الحفظ):" }));
    const ul = h("ul");
    list.forEach(function (x) { ul.append(h("li", { text: x })); });
    e.append(ul);
    e.classList.remove("hidden");
  }

  function syncCategoryFields() {
    const cat = $("#fCat").value;
    const src = needsSources(cat);
    $("#fSourcesWrap").classList.toggle("hidden", !src);
    $("#fAddSrc").disabled = !src;
    const horror = cat === "story_horror";
    $("#fWarningWrap").classList.toggle("hidden", !horror);
    $("#fWarning").disabled = !horror;
    if (!horror) $("#fWarning").value = "";
    $("#fTagsWrap").classList.toggle("hidden", !isStoryCat(cat));
    $("#fHint").textContent = wordHint(cat);
    updWords();
  }

  function renderVideo(a) {
    const box = $("#fVideo");
    box.innerHTML = "";
    const v = a && a.video && typeof a.video === "object" ? a.video : null;
    if (!v || !(v.url || v.page || v.poster || v.seconds)) {
      box.append(document.createTextNode("لا يوجد فيلم لهذه القصة بعد."));
      return;
    }
    [["url", v.url], ["page", v.page], ["poster", v.poster], ["seconds", v.seconds]].forEach(function (p) {
      if (p[1] === undefined || p[1] === null || p[1] === "") return;
      box.append(h("div", { dir: p[0] === "seconds" ? "auto" : "ltr" },
        h("b", { text: p[0] + ": " }), document.createTextNode(String(p[1]))));
    });
  }

  function openEditor(id, presetCat) {
    fillSelects();
    let a = null, cat = presetCat || S.cat, fromCat = null;
    if (id) {
      const f = locate(id);
      if (f) { a = f.a; fromCat = f.cat; cat = presetCat || f.cat; }
    }
    S.editing = a ? { id: a.id, cat: fromCat } : null;
    S.editImage = a ? (a.image || "") : "";
    S.pendingFile = null;
    S.editSources = a && Array.isArray(a.sources) && a.sources.length
      ? a.sources.map(function (s) { return { publisher: (s && s.publisher) || "", url: (s && s.url) || "" }; })
      : [{ publisher: "", url: "" }];
    $("#edTitle").textContent = a ? "تعديل القصة أو المقال" : "قصة جديدة";
    $("#fTitle").value = a ? (a.title || "") : "";
    $("#fSummary").value = a ? (a.summary || "") : "";
    $("#fCat").value = cat;
    $("#fDate").value = toLocalInput(a ? a.date : Date.now());
    $("#fBody").value = a ? (a.content || "") : "";
    const tags = a && Array.isArray(a.tags) ? a.tags : [];
    TAG_FIELDS.forEach(function (t) { $(t[1]).checked = tags.indexOf(t[0]) >= 0; });
    $("#fHashtags").value = a && Array.isArray(a.hashtags) ? a.hashtags.join(" ") : "";
    $("#fWarning").value = (a && a.warning) || "";
    $("#fVideo").innerHTML = "";
    renderVideo(a);
    $("#fCredit").value = (a && a.image_credit && (a.image_credit.author || a.image_credit.source)) || "نكسوس";
    $("#fManual").checked = a ? !!a.manual : true;
    syncCategoryFields();
    $("#fAuto").checked = !(a && a.image);
    $("#fFile").value = "";
    setPreview(a ? a.image : "");
    clearFormMsgs();
    renderSources();
    $("#modal").classList.remove("hidden");
    setTimeout(function () { $("#fTitle").focus(); }, 60);
  }

  function closeEditor() {
    if (S.pendingFile && !confirm("الصورة الجديدة لم تُرفع بعد؛ إغلاق النموذج سيتجاهلها. متابعة؟")) return;
    $("#modal").classList.add("hidden");
    S.pendingFile = null;
    S.editImage = "";
  }

  function renderSources() {
    const box = $("#fSources");
    box.innerHTML = "";
    S.editSources.forEach(function (s, idx) {
      const row = h("div", { class: "srcrow" },
        h("input", { value: s.publisher, placeholder: "اسم المصدر", oninput: function (e) { s.publisher = e.target.value; } }),
        h("input", { value: s.url, placeholder: "https://…", dir: "ltr", oninput: function (e) { s.url = e.target.value; } }),
        h("button", {
          class: "btn ghost tiny", type: "button", title: "حذف المصدر",
          onclick: function () {
            S.editSources.splice(idx, 1);
            if (!S.editSources.length) S.editSources.push({ publisher: "", url: "" });
            renderSources();
          }
        }, "✕"));
      box.append(row);
    });
  }

  function updWords() {
    const n = words($("#fBody").value);
    const cat = $("#fCat").value || CATS[0][0];
    const el = $("#fWords");
    el.textContent = n + " كلمة / المستحسن " + minWords(cat) + "–" + maxWords(cat);
    el.className = "wc " + (n >= minWords(cat) && n <= maxWords(cat) ? "ok" : "warn");
  }

  async function compressImage(file) {
    const bmp = await createImageBitmap(file);
    const w0 = bmp.width, h0 = bmp.height;
    const scale = Math.min(1, 1600 / w0);
    const w = Math.max(1, Math.round(w0 * scale));
    const hh = Math.max(1, Math.round(h0 * scale));
    const cv = document.createElement("canvas");
    cv.width = w; cv.height = hh;
    cv.getContext("2d").drawImage(bmp, 0, 0, w, hh);
    const blob = await new Promise(function (res) { cv.toBlob(function (b) { res(b); }, "image/webp", 0.86); });
    if (!blob) throw new Error("تعذّر ضغط الصورة في هذا المتصفح");
    return { blob: blob, w: w0, h: h0 };
  }

  async function onFile(ev) {
    const f = ev.target.files && ev.target.files[0];
    if (!f) return;
    try {
      const r = await compressImage(f);
      if (r.w < 640 || r.h < 320) {
        formErr(["الصورة أصغر من 640×320 بكسل — اختر صورة أكبر."]);
        ev.target.value = "";
        return;
      }
      const buf = await r.blob.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let bin = "";
      for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
      S.pendingFile = btoa(bin);
      $("#fAuto").checked = false;
      const box = $("#fPrev");
      box.innerHTML = "";
      box.append(h("img", { src: URL.createObjectURL(r.blob), alt: "" }));
      clearFormMsgs();
      toast("الصورة جاهزة (" + Math.round(r.blob.size / 1024) + " كيلوبايت) — ستُرفع عند الحفظ.", "ok");
    } catch (e) {
      formErr(["تعذّر قراءة الصورة: " + e.message]);
    }
  }

  function validate(v) {
    const errors = [], warnings = [];
    if (v.title.length < 15) errors.push("العنوان قصير جداً (15 حرفاً على الأقل).");
    if (v.title.length > 115) errors.push("العنوان طويل جداً (115 حرفاً كحد أقصى).");
    if (arabicRatio(v.title) < 0.5) errors.push("العنوان يجب أن يكون بالعربية.");
    if (v.summary.length < 40) errors.push("الملخص قصير جداً (40 حرفاً على الأقل) — يظهر في الرئيسية وقائمة المقالات.");
    if (v.summary.length > 320) errors.push("الملخص طويل جداً (320 حرفاً كحد أقصى).");
    const wc = words(v.body);
    const lo = minWords(v.cat), hi = maxWords(v.cat);
    if (wc < lo) warnings.push("عدد الكلمات " + wc + " أقل من المستحسن (" + lo + " لهذا القسم) — يمكنك الحفظ كمسودة.");
    else if (wc > hi) warnings.push("عدد الكلمات " + wc + " أطول من المستحسن (" + hi + " لهذا القسم) — راجع الطول.");
    if (needsSources(v.cat)) {
      const srcs = v.sources || [];
      if (!srcs.length) errors.push("أضف مصدراً واحداً على الأقل برابط http.");
      srcs.forEach(function (s) {
        if (!/^https?:\/\//i.test(s.url)) errors.push("رابط مصدر غير صالح: " + (s.url || "(فارغ)"));
      });
      if (srcs.length && srcs.length < 2) warnings.push("مصدر واحد فقط: المستحسن مصدران على الأقل.");
    }
    if (v.cat === "story_horror" && !String(v.warning || "").trim()) {
      warnings.push("قصص الرعب النفسي تحتاج تنبيه واضح في الأعلى — أضف نص التنبيه.");
    }
    if (isKidCat(v.cat)) {
      ["رعب", "قتل", "دم", "سلاح"].forEach(function (w) {
        if (String(v.body).indexOf(w) >= 0) warnings.push("ركن الأطفال: وردت كلمة «" + w + "» في النص — راجع السلامة العائلية.");
      });
    }
    if (!v.auto && !S.pendingFile && !S.editImage) warnings.push("لا صورة: سيرسم الباني رسماً توضيحياً أصلياً بدل صورة المقال.");
    if (!v.manual) warnings.push("أزلت التثبيت اليدوي: البوت قد ينقل المقال أو يعيد ترتيبه حسب التاريخ.");
    return { errors: errors, warnings: warnings };
  }

  async function editorSave() {
    clearFormMsgs();
    const v = {
      title: $("#fTitle").value.trim(),
      summary: $("#fSummary").value.trim(),
      cat: $("#fCat").value,
      date: fromLocalInput($("#fDate").value),
      body: $("#fBody").value,
      sources: S.editSources.map(function (s) { return { publisher: s.publisher.trim(), url: s.url.trim() }; })
        .filter(function (s) { return s.publisher || s.url; }),
      tags: TAG_FIELDS.filter(function (t) { return $(t[1]).checked; }).map(function (t) { return t[0]; }),
      hashtags: $("#fHashtags").value.trim().split(/[\s,،]+/).filter(Boolean)
        .map(function (h) { return h.charAt(0) === "#" ? h : "#" + h; }).slice(0, 10),
      warning: $("#fWarning").value.trim(),
      manual: $("#fManual").checked,
      credit: $("#fCredit").value.trim() || "نكسوس",
      auto: $("#fAuto").checked
    };
    const res = validate(v);
    if (res.warnings.length) formWarn(res.warnings);
    if (res.errors.length) { formErr(res.errors); return; }

    const id = S.editing ? S.editing.id : newId(v.cat);
    let imagePath = S.editImage || "";
    if (S.pendingFile) {
      setBusy(true, "جارٍ رفع الصورة…");
      try {
        imagePath = "images/" + id + ".webp";
        await putFile("images/" + id + ".webp", S.pendingFile, "صورة مقال يدوي: " + id);
        S.pendingFile = null;
        toast("رُفعت الصورة إلى المستودع.", "ok");
      } catch (e) {
        setBusy(false);
        formErr(["فشل رفع الصورة: " + e.message]);
        return;
      }
      setBusy(false);
    }
    if (v.auto) imagePath = "";

    const content = v.body.replace(/\r/g, "").split(/\n\s*\n/)
      .map(function (p) { return p.trim().replace(/\s*\n\s*/g, " "); })
      .filter(Boolean).join("\n\n");

    const old = S.editing ? locate(S.editing.id) : null;
    const base = old && old.a ? old.a : {};
    const oldCredit = base.image_credit && typeof base.image_credit === "object" ? base.image_credit : {};
    // انسخ كل الحقول الأصلية أولاً (scenes و video و image_kind و style وأي حقل غير معروف)
    // ثم استبدل الحقول التي حرّرها المستخدم فقط، حتى لا يُسقَط شيء عند الحفظ.
    const entry = Object.assign({}, base, {
      id: id,
      title: v.title,
      summary: v.summary,
      content: content,
      date: v.date,
      image: imagePath,
      image_alt: v.title,
      image_prompt: base.image_prompt || "كتابة نكسوس",
      image_credit: Object.assign({}, oldCredit, {
        kind: oldCredit.kind || (imagePath ? "photo" : "svg"),
        source: v.credit, author: v.credit
      }),
      manual: v.manual,
      cat_ok: true
    });
    if (isStoryCat(v.cat)) entry.tags = v.tags;
    if (v.hashtags.length) entry.hashtags = v.hashtags;
    else delete entry.hashtags;
    if (v.cat === "story_horror") entry.warning = v.warning;
    else delete entry.warning;
    if (needsSources(v.cat)) entry.sources = v.sources;
    else delete entry.sources;
    if (old) {
      const fromCat = old.cat;
      S.data.articles[fromCat][old.i] = entry;
      if (fromCat !== v.cat) {
        S.data.articles[fromCat].splice(old.i, 1);
        S.data.articles[v.cat].unshift(entry);
      }
      S.ops.push({ t: "update", id: id, cat: v.cat, fromCat: fromCat, a: clone(entry) });
      snapshotOrder(fromCat);
      if (fromCat !== v.cat) snapshotOrder(v.cat);
    } else {
      S.data.articles[v.cat].unshift(entry);
      S.ops.push({ t: "add", cat: v.cat, a: clone(entry) });
      snapshotOrder(v.cat);
    }
    mark();
    $("#modal").classList.add("hidden");
    S.cat = v.cat;
    renderAll();
    toast("حُفظ التغيير في هذه الصفحة — اضغط «حفظ ونشر» لرفعه إلى الموقع.", "warn");
  }

  // ---------------------------------------------------------------- events + boot
  function bind() {
    $("#setupForm").addEventListener("submit", setupSubmit);
    $("#lockForm").addEventListener("submit", lockSubmit);
    $("#sForget").addEventListener("click", function () {
      if (confirm("مسح كل الإعدادات المحفوظة في هذا المتصفح؟")) { lsDel(CFG_KEY); lsDel(PAT_KEY); lsDel(PIN_KEY); location.reload(); }
    });
    $("#lForgot").addEventListener("click", function () {
      if (!confirm("سيُمسح المفتاح والرمز من هذا المتصفح (الموقع نفسه يبقى سليماً). ستحتاج إلى مفتاح GitHub جديد. متابعة؟")) return;
      lsDel(CFG_KEY); lsDel(PAT_KEY); lsDel(PIN_KEY);
      S.cfg = { repo: "", branch: "main", workflow: "rebuild.yml" };
      S.pat = ""; S.pin = "";
      showSetup(false);
    });
    $("#bNew").addEventListener("click", function () { openEditor(null); });
    $("#bSave").addEventListener("click", commit);
    $("#bReload").addEventListener("click", async function () {
      if (S.dirty && !confirm("إعادة التحميل ستُفقد التعديلات غير المحفوظة. متابعة؟")) return;
      setStatus("جارٍ التحديث…", "warn");
      try { await loadDoc(); renderAll(); setStatus("متصل", "ok"); toast("حُدّثت القائمة من GitHub.", "ok"); }
      catch (e) { handleErr(e); }
    });
    $("#bLock").addEventListener("click", lockPanel);
    $("#bSet").addEventListener("click", openSettings);
    $("#q").addEventListener("input", renderList);
    $("#moveCancel").addEventListener("click", function () { $("#mover").classList.add("hidden"); });
    $("#edClose").addEventListener("click", closeEditor);
    $("#edCancel").addEventListener("click", closeEditor);
    $("#edSave").addEventListener("click", editorSave);
    $("#fCat").addEventListener("change", syncCategoryFields);
    $("#fBody").addEventListener("input", updWords);
    $("#fFile").addEventListener("change", onFile);
    $("#fAuto").addEventListener("change", function () {
      if ($("#fAuto").checked) { S.pendingFile = null; $("#fFile").value = ""; setPreview(""); }
    });
    $("#fAddSrc").addEventListener("click", function () { S.editSources.push({ publisher: "", url: "" }); renderSources(); });
    $("#gSave").addEventListener("click", saveSettings);
    $("#gClose").addEventListener("click", function () { $("#settings").classList.add("hidden"); });
    $("#gBackup").addEventListener("click", backup);
    $("#gWipe").addEventListener("click", wipe);
    ["#mover", "#settings"].forEach(function (s) {
      $(s).addEventListener("click", function (ev) { if (ev.target === $(s)) $(s).classList.add("hidden"); });
    });
    window.addEventListener("beforeunload", function (e) {
      if (S.dirty) { e.preventDefault(); e.returnValue = ""; }
    });
  }

  function boot() {
    fillSelects();
    let cfg = null;
    try { cfg = JSON.parse(lsGet(CFG_KEY) || "null"); } catch (e) {}
    if (cfg && cfg.repo) S.cfg = { repo: cfg.repo, branch: cfg.branch || "main", workflow: cfg.workflow || "rebuild.yml" };
    S.pat = lsGet(PAT_KEY) || "";
    S.pin = lsGet(PIN_KEY) || "";
    bind();
    if (!S.cfg.repo || !S.pat || !S.pin) showSetup(false);
    else showLock();
  }

  document.addEventListener("DOMContentLoaded", boot);

  /* للاختبار من console فقط */
  window.NP = {
    S: S, validate: validate, applyOps: applyOps, words: words,
    sha256: sha256, newId: newId
  };
})();
