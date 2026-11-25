/**
 * 関西・全国 能楽公演ガイド フロントエンド制御スクリプト
 * - 初期表示は「関西すべて」
 * - 検索・エリア・月・特徴フィルター
 * - 一覧 / カレンダー / お気に入り（localStorage保存）の切り替え
 * - iPhoneでの片手操作を意識したボトムシート詳細表示
 */

(() => {
  "use strict";

  const FAV_STORAGE_KEY = "kansai_noh_favorites_v1";
  const KANSAI_OTHERS = ["奈良", "滋賀", "和歌山"];

  // アプリケーション状態
  const state = {
    data: null,
    performances: [],
    selectedArea: "kansai", // 初期表示は関西
    selectedMonth: "all",
    searchQuery: "",
    quickFilters: new Set(),
    activeView: "list",     // list | calendar | favorites
    favorites: new Set(),
    calYear: new Date().getFullYear(),
    calMonth: new Date().getMonth() + 1,
    calSelectedDate: "",
    modalItem: null,
  };

  // DOM要素参照
  const el = {
    updatedInfo: document.getElementById("updated-info"),
    searchInput: document.getElementById("search-input"),
    clearSearchBtn: document.getElementById("clear-search-btn"),
    monthSelect: document.getElementById("month-select"),
    areaChips: document.getElementById("area-chips"),
    quickFilters: document.getElementById("quick-filters"),
    resultCount: document.getElementById("result-count"),
    resetFiltersBtn: document.getElementById("reset-filters-btn"),
    viewList: document.getElementById("view-list"),
    viewCalendar: document.getElementById("view-calendar"),
    viewFavorites: document.getElementById("view-favorites"),
    performanceList: document.getElementById("performance-list"),
    emptyState: document.getElementById("empty-state"),
    calPrevBtn: document.getElementById("cal-prev-btn"),
    calNextBtn: document.getElementById("cal-next-btn"),
    calMonthTitle: document.getElementById("cal-month-title"),
    calendarGrid: document.getElementById("calendar-grid"),
    calSelectedDateTitle: document.getElementById("cal-selected-date-title"),
    calendarDayList: document.getElementById("calendar-day-list"),
    favoritesList: document.getElementById("favorites-list"),
    favoritesEmpty: document.getElementById("favorites-empty"),
    favNavBadge: document.getElementById("fav-nav-badge"),
    detailModal: document.getElementById("detail-modal"),
    modalPrefBadge: document.getElementById("modal-pref-badge"),
    modalBody: document.getElementById("modal-body"),
    modalCloseBtn: document.getElementById("modal-close-btn"),
    modalFavBtn: document.getElementById("modal-fav-btn"),
    modalOfficialLink: document.getElementById("modal-official-link"),
    openSourcesBtn: document.getElementById("open-sources-btn"),
    sourcesModal: document.getElementById("sources-modal"),
    sourcesCloseBtn: document.getElementById("sources-close-btn"),
    sourcesBody: document.getElementById("sources-body"),
  };

  // HTMLエスケープ
  function esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // 外部リンクのURL安全性チェック（http / https のみ許可）
  function safeUrl(rawUrl) {
    try {
      const parsed = new URL(String(rawUrl || "").trim());
      if (parsed.protocol === "https:" || parsed.protocol === "http:") {
        return parsed.href;
      }
    } catch {
      // 不正なURLは無効扱いとする
    }
    return "";
  }

  // お気に入りの読み込み・保存
  function loadFavorites() {
    try {
      const saved = JSON.parse(localStorage.getItem(FAV_STORAGE_KEY) || "[]");
      state.favorites = new Set(Array.isArray(saved) ? saved : []);
    } catch {
      state.favorites = new Set();
    }
  }

  function saveFavorites() {
    try {
      localStorage.setItem(FAV_STORAGE_KEY, JSON.stringify([...state.favorites]));
    } catch {
      // プライベートブラウズ等で保存不可の場合は無視
    }
    updateFavBadge();
  }

  function updateFavBadge() {
    const count = state.favorites.size;
    el.favNavBadge.textContent = String(count);
    el.favNavBadge.classList.toggle("hidden", count === 0);
  }

  function toggleFavorite(id) {
    if (state.favorites.has(id)) {
      state.favorites.delete(id);
    } else {
      state.favorites.add(id);
    }
    saveFavorites();
    renderAll();
    if (state.modalItem && state.modalItem.id === id) {
      updateModalFavButton();
    }
  }

  // データの読み込み（サーバー経由ならJSON、直接起動ならwindow.NOH_DATAを使用）
  async function loadData() {
    try {
      if (window.location.protocol !== "file:") {
        const res = await fetch("data/performances.json", { cache: "no-store" });
        if (res.ok) {
          return await res.json();
        }
      }
    } catch {
      // フォールバックへ
    }
    return window.NOH_DATA || { updatedAt: "未取得", sources: [], performances: [] };
  }

  // エリア条件の判定
  function matchesArea(item, areaKey) {
    if (areaKey === "all") return true;
    if (areaKey === "kansai") return item.region === "関西";
    if (areaKey === "kansai_other") return KANSAI_OTHERS.includes(item.prefecture);
    return item.prefecture === areaKey;
  }

  // 日付の曜日判定（0:日, 6:土）
  function getDayOfWeek(dateStr) {
    const [y, m, d] = dateStr.split("-").map(Number);
    return new Date(y, m - 1, d).getDay();
  }

  // 現在のフィルター条件で公演を絞り込む
  function getFilteredPerformances() {
    const q = state.searchQuery.trim().toLowerCase();
    return state.performances.filter((item) => {
      if (!matchesArea(item, state.selectedArea)) return false;
      if (state.selectedMonth !== "all" && !item.date.startsWith(state.selectedMonth)) return false;

      if (state.quickFilters.has("beginner")) {
        const hay = `${item.title} ${item.summary} ${(item.tags || []).join(" ")}`;
        if (!/解説|初心者|体験|レクチャー|講座|入門/.test(hay)) return false;
      }
      if (state.quickFilters.has("weekend")) {
        const dow = getDayOfWeek(item.date);
        if (dow !== 0 && dow !== 6) return false;
      }
      if (state.quickFilters.has("free")) {
        const hay = `${item.price} ${(item.tags || []).join(" ")} ${item.title}`;
        if (!/無料/.test(hay)) return false;
      }

      if (q) {
        const target = [
          item.title,
          item.venue,
          item.prefecture,
          item.source,
          item.summary,
          ...(item.programs || []),
          ...(item.tags || []),
        ]
          .join(" ")
          .toLowerCase();
        if (!target.includes(q)) return false;
      }
      return true;
    });
  }

  // エリアチップの描画
  function renderAreaChips() {
    const areas = [
      { key: "kansai", label: "関西すべて" },
      { key: "大阪", label: "大阪" },
      { key: "京都", label: "京都" },
      { key: "兵庫", label: "兵庫" },
      { key: "kansai_other", label: "奈良・滋賀・和歌山" },
      { key: "all", label: "全国すべて" },
    ];

    el.areaChips.innerHTML = areas
      .map((a) => {
        const count = state.performances.filter((it) => matchesArea(it, a.key)).length;
        const active = state.selectedArea === a.key ? "active" : "";
        return `
          <button type="button" class="area-chip ${active}" data-area="${a.key}" role="tab" aria-selected="${Boolean(active)}">
            <span>${esc(a.label)}</span>
            <span class="chip-count">${count}</span>
          </button>
        `;
      })
      .join("");
  }

  // 月セレクトボックスの構築
  function buildMonthSelect() {
    const months = [...new Set(state.performances.map((p) => p.date.slice(0, 7)))].sort();
    const opts = ['<option value="all">すべての月</option>'];
    for (const ym of months) {
      const [y, m] = ym.split("-");
      opts.push(`<option value="${ym}">${y}年${Number(m)}月</option>`);
    }
    el.monthSelect.innerHTML = opts.join("");
  }

  // 公演カード1件のHTML生成
  function createCardHtml(item) {
    const [, m, d] = item.date.split("-").map(Number);
    const dow = getDayOfWeek(item.date);
    const wdNames = ["日", "月", "火", "水", "木", "金", "土"];
    const wdClass = dow === 0 ? "is-sun" : dow === 6 ? "is-sat" : "";
    const isFav = state.favorites.has(item.id);
    const prefClass = item.region === "関西" ? "badge-kansai" : "badge-other";

    const tagsHtml = (item.tags || [])
      .slice(0, 2)
      .map((t) => `<span class="badge badge-tag">${esc(t)}</span>`)
      .join("");

    const programsHtml =
      item.programs && item.programs.length > 0
        ? `<div class="card-programs">${item.programs
            .slice(0, 3)
            .map((p) => `<div>${esc(p)}</div>`)
            .join("")}</div>`
        : "";

    return `
      <article class="perf-card" data-id="${esc(item.id)}">
        <div class="date-box ${wdClass}">
          <span class="date-month">${m}月</span>
          <span class="date-day">${d}</span>
          <span class="date-wd">(${wdNames[dow]})</span>
        </div>
        <div class="card-body">
          <div class="card-top-row">
            <div class="card-badges">
              <span class="badge ${prefClass}">${esc(item.prefecture)}</span>
              ${tagsHtml}
            </div>
            <button type="button" class="fav-btn ${isFav ? "active" : ""}" data-fav-id="${esc(item.id)}" aria-label="お気に入り切替">
              ${isFav ? "♥" : "♡"}
            </button>
          </div>
          <h3 class="card-title">${esc(item.title)}</h3>
          <div class="card-meta">
            <span>📍 ${esc(item.venue)}</span>
            ${item.time ? `<span>🕒 ${esc(item.time)}</span>` : ""}
          </div>
          ${programsHtml}
          <div class="card-source">情報元：${esc(item.source)}</div>
        </div>
      </article>
    `;
  }

  // 一覧ビューの描画
  function renderListView(filtered) {
    if (filtered.length === 0) {
      el.performanceList.innerHTML = "";
      el.emptyState.classList.remove("hidden");
      return;
    }
    el.emptyState.classList.add("hidden");

    // 月ごとに見出しを挟んで見やすく表示
    let currentYm = "";
    const chunks = [];
    for (const item of filtered) {
      const ym = item.date.slice(0, 7);
      if (ym !== currentYm) {
        currentYm = ym;
        const [y, m] = ym.split("-");
        chunks.push(`<div class="month-divider">${y}年 ${Number(m)}月</div>`);
      }
      chunks.push(createCardHtml(item));
    }
    el.performanceList.innerHTML = chunks.join("");
  }

  // カレンダービューの描画
  function renderCalendarView(filtered) {
    const y = state.calYear;
    const m = state.calMonth;
    el.calMonthTitle.textContent = `${y}年 ${m}月`;

    // 日付ごとの公演マップを作成
    const byDate = new Map();
    for (const item of filtered) {
      if (!byDate.has(item.date)) byDate.set(item.date, []);
      byDate.get(item.date).push(item);
    }

    const firstDow = new Date(y, m - 1, 1).getDay();
    const daysInMonth = new Date(y, m, 0).getDate();
    const todayIso = new Date().toISOString().slice(0, 10);

    const cells = [];
    for (let i = 0; i < firstDow; i++) {
      cells.push('<div class="cal-cell empty"></div>');
    }

    for (let d = 1; d <= daysInMonth; d++) {
      const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const list = byDate.get(iso) || [];
      const classes = ["cal-cell"];
      if (list.length > 0) classes.push("has-events");
      if (iso === state.calSelectedDate) classes.push("selected");
      if (iso === todayIso) classes.push("today");

      cells.push(`
        <button type="button" class="${classes.join(" ")}" data-cal-date="${iso}">
          <span class="cal-day-num">${d}</span>
          ${list.length > 0 ? `<span class="cal-dot-count">${list.length}</span>` : ""}
        </button>
      `);
    }
    el.calendarGrid.innerHTML = cells.join("");

    // 選択日の公演リスト描画
    if (state.calSelectedDate) {
      const dayItems = byDate.get(state.calSelectedDate) || [];
      const [sy, sm, sd] = state.calSelectedDate.split("-").map(Number);
      el.calSelectedDateTitle.textContent = `${sy}年${sm}月${sd}日の公演（${dayItems.length}件）`;
      el.calendarDayList.innerHTML =
        dayItems.length > 0
          ? dayItems.map(createCardHtml).join("")
          : '<div class="empty-state"><p class="empty-desc">この日の該当公演はありません。</p></div>';
    } else {
      el.calSelectedDateTitle.textContent = "数字（件数）がついた日付をタップしてください";
      el.calendarDayList.innerHTML = "";
    }
  }

  // お気に入りビューの描画
  function renderFavoritesView() {
    const favItems = state.performances.filter((p) => state.favorites.has(p.id));
    if (favItems.length === 0) {
      el.favoritesList.innerHTML = "";
      el.favoritesEmpty.classList.remove("hidden");
    } else {
      el.favoritesEmpty.classList.add("hidden");
      el.favoritesList.innerHTML = favItems.map(createCardHtml).join("");
    }
  }

  // 詳細モーダルを開く
  function openDetailModal(item) {
    state.modalItem = item;
    el.modalPrefBadge.textContent = `${item.region}・${item.prefecture}`;
    el.modalPrefBadge.className = `badge ${item.region === "関西" ? "badge-kansai" : "badge-other"}`;

    const programsHtml =
      item.programs && item.programs.length > 0
        ? `<ul class="detail-programs">${item.programs.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`
        : "公式サイトをご確認ください";

    const tagsHtml =
      item.tags && item.tags.length > 0
        ? `<div class="card-badges modal-tags-wrap">${item.tags
            .map((t) => `<span class="badge badge-tag">${esc(t)}</span>`)
            .join("")}</div>`
        : "";

    el.modalBody.innerHTML = `
      <h2 id="modal-title" class="detail-title">${esc(item.title)}</h2>
      ${tagsHtml}
      <table class="detail-table">
        <tr><th>日程</th><td>${esc(item.dateLabel)}</td></tr>
        ${item.time ? `<tr><th>時間</th><td>${esc(item.time)}</td></tr>` : ""}
        <tr><th>会場</th><td>${esc(item.venue)}（${esc(item.prefecture)}）</td></tr>
        <tr><th>演目</th><td>${programsHtml}</td></tr>
        ${item.price ? `<tr><th>料金</th><td>${esc(item.price)}</td></tr>` : ""}
        <tr><th>情報元</th><td>${esc(item.source)}</td></tr>
      </table>
      ${item.summary ? `<p class="detail-summary">${esc(item.summary)}</p>` : ""}
    `;

    // http / https の安全なURLのみリンクとして有効化
    const validUrl = safeUrl(item.url);
    if (validUrl) {
      el.modalOfficialLink.href = validUrl;
      el.modalOfficialLink.textContent = "公式サイトで詳細を見る ↗";
      el.modalOfficialLink.classList.remove("is-disabled");
      el.modalOfficialLink.removeAttribute("aria-disabled");
    } else {
      el.modalOfficialLink.removeAttribute("href");
      el.modalOfficialLink.textContent = "公式リンクなし";
      el.modalOfficialLink.classList.add("is-disabled");
      el.modalOfficialLink.setAttribute("aria-disabled", "true");
    }
    updateModalFavButton();
    el.detailModal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }

  function updateModalFavButton() {
    if (!state.modalItem) return;
    const isFav = state.favorites.has(state.modalItem.id);
    el.modalFavBtn.textContent = isFav ? "♥ 保存済み" : "♡ お気に入り";
    el.modalFavBtn.classList.toggle("active", isFav);
  }

  function closeModals() {
    el.detailModal.classList.add("hidden");
    el.sourcesModal.classList.add("hidden");
    document.body.style.overflow = "";
  }

  // 情報源モーダルを開く
  function openSourcesModal() {
    const sources = (state.data && state.data.sources) || [];
    el.sourcesBody.innerHTML = `
      <p class="sources-updated">
        最終更新：${esc(state.data ? state.data.updatedAt : "-")}
      </p>
      <ul class="source-list">
        ${sources
          .map(
            (s) => `
          <li class="source-item">
            <span>${esc(s.name)}</span>
            <span class="source-count">${s.count}件</span>
          </li>`
          )
          .join("")}
      </ul>
      <p class="sources-note">
        ※重複する公演は自動で整理しています。最新のチケット状況や開演時間は各公式サイトをご確認ください。
      </p>
    `;
    el.sourcesModal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }

  // 全体再描画
  function renderAll() {
    const filtered = getFilteredPerformances();
    const hasCustomFilter =
      state.selectedArea !== "kansai" ||
      state.selectedMonth !== "all" ||
      state.searchQuery.trim() !== "" ||
      state.quickFilters.size > 0;

    el.resetFiltersBtn.classList.toggle("hidden", !hasCustomFilter);

    if (state.activeView === "favorites") {
      el.resultCount.textContent = `お気に入り：${state.favorites.size}件`;
    } else {
      el.resultCount.textContent = `表示中：${filtered.length}件（全${state.performances.length}件）`;
    }

    el.viewList.classList.toggle("hidden", state.activeView !== "list");
    el.viewCalendar.classList.toggle("hidden", state.activeView !== "calendar");
    el.viewFavorites.classList.toggle("hidden", state.activeView !== "favorites");

    renderAreaChips();
    if (state.activeView === "list") renderListView(filtered);
    if (state.activeView === "calendar") renderCalendarView(filtered);
    if (state.activeView === "favorites") renderFavoritesView();
  }

  // イベント登録
  function bindEvents() {
    // 検索入力
    el.searchInput.addEventListener("input", (e) => {
      state.searchQuery = e.target.value;
      el.clearSearchBtn.classList.toggle("hidden", !state.searchQuery);
      renderAll();
    });

    el.clearSearchBtn.addEventListener("click", () => {
      state.searchQuery = "";
      el.searchInput.value = "";
      el.clearSearchBtn.classList.add("hidden");
      renderAll();
    });

    // 月フィルター
    el.monthSelect.addEventListener("change", (e) => {
      state.selectedMonth = e.target.value;
      if (state.selectedMonth !== "all") {
        const [y, m] = state.selectedMonth.split("-").map(Number);
        state.calYear = y;
        state.calMonth = m;
      }
      renderAll();
    });

    // エリアチップ
    el.areaChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".area-chip");
      if (!btn) return;
      state.selectedArea = btn.dataset.area;
      renderAll();
    });

    // クイックフィルター
    el.quickFilters.addEventListener("click", (e) => {
      const btn = e.target.closest(".quick-chip");
      if (!btn) return;
      const key = btn.dataset.filter;
      if (state.quickFilters.has(key)) {
        state.quickFilters.delete(key);
        btn.classList.remove("active");
      } else {
        state.quickFilters.add(key);
        btn.classList.add("active");
      }
      renderAll();
    });

    // リセットボタン
    el.resetFiltersBtn.addEventListener("click", () => {
      state.selectedArea = "kansai";
      state.selectedMonth = "all";
      state.searchQuery = "";
      state.quickFilters.clear();
      el.searchInput.value = "";
      el.monthSelect.value = "all";
      el.clearSearchBtn.classList.add("hidden");
      document.querySelectorAll(".quick-chip").forEach((b) => b.classList.remove("active"));
      renderAll();
    });

    // カードクリック＆お気に入りボタン（委譲）
    document.addEventListener("click", (e) => {
      const favBtn = e.target.closest("[data-fav-id]");
      if (favBtn) {
        e.stopPropagation();
        toggleFavorite(favBtn.dataset.favId);
        return;
      }

      const card = e.target.closest(".perf-card");
      if (card) {
        const item = state.performances.find((p) => p.id === card.dataset.id);
        if (item) openDetailModal(item);
      }
    });

    // カレンダー操作
    el.calPrevBtn.addEventListener("click", () => {
      state.calMonth -= 1;
      if (state.calMonth < 1) {
        state.calMonth = 12;
        state.calYear -= 1;
      }
      state.calSelectedDate = "";
      renderAll();
    });

    el.calNextBtn.addEventListener("click", () => {
      state.calMonth += 1;
      if (state.calMonth > 12) {
        state.calMonth = 1;
        state.calYear += 1;
      }
      state.calSelectedDate = "";
      renderAll();
    });

    el.calendarGrid.addEventListener("click", (e) => {
      const cell = e.target.closest("[data-cal-date]");
      if (!cell) return;
      state.calSelectedDate = cell.dataset.calDate;
      renderAll();
    });

    // 下部タブ切替
    document.querySelectorAll(".bottom-nav .nav-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.activeView = btn.dataset.view;
        document.querySelectorAll(".bottom-nav .nav-item").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        window.scrollTo({ top: 0, behavior: "smooth" });
        renderAll();
      });
    });

    // モーダル閉じる
    el.modalCloseBtn.addEventListener("click", closeModals);
    el.sourcesCloseBtn.addEventListener("click", closeModals);
    el.openSourcesBtn.addEventListener("click", openSourcesModal);
    el.modalFavBtn.addEventListener("click", () => {
      if (state.modalItem) toggleFavorite(state.modalItem.id);
    });

    [el.detailModal, el.sourcesModal].forEach((backdrop) => {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) closeModals();
      });
    });
  }

  // 初期化
  async function init() {
    loadFavorites();
    updateFavBadge();
    bindEvents();

    const data = await loadData();
    state.data = data;
    state.performances = data.performances || [];
    el.updatedInfo.textContent = `最終更新：${data.updatedAt || "未取得"}（関西 ${data.kansaiCount || 0}件 / 全国 ${data.totalCount || 0}件）`;

    buildMonthSelect();
    // 最初の公演の月をカレンダー初期表示にする
    if (state.performances.length > 0) {
      const [y, m] = state.performances[0].date.split("-").map(Number);
      state.calYear = y;
      state.calMonth = m;
    }
    renderAll();
  }

  init();
})();
