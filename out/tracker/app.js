/* CalorieBase Tracker — vanilla JS, no dependencies, data stays on-device. */
(function () {
  'use strict';

  var DB_URL = '/foods.json';
  var LS_KEY = 'cbtracker.v1';
  var MEALS = ['Breakfast', 'Lunch', 'Dinner', 'Snacks'];

  var DB = [];
  var CATS = [];
  var NORM = [];
  var TOK = [];
  var SEG = [];
  var ready = false;

  var state = { settings: null, days: {} };
  var currentDate = todayISO();

  var DEFAULT_SETTINGS = {
    sex: 'female', age: 30, heightCm: 165, weightKg: 65,
    activity: 1.375, goal: 'maintain', proteinPerKg: 1.8, fatPct: 27
  };

  /* ---------- helpers ---------- */
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function iso(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function parseISO(s) { var p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function todayISO() { return iso(new Date()); }
  function r0(n) { return Math.round(n); }
  function r1(n) { return Math.round(n * 10) / 10; }
  function num(n, d) { if (n === null || n === undefined || isNaN(n)) return '\u2014'; return Number(n).toFixed(d || 0); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function norm(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(); }
  function plural(w) {
    if (w.length > 4 && w.slice(-3) === 'ies') return w.slice(0, -3) + 'y';
    if (/(ches|shes|sses|xes|zes|oes)$/.test(w)) return w.slice(0, -2);
    if (w.slice(-1) === 's' && w.slice(-2) !== 'ss') return w.slice(0, -1);
    return w;
  }
  function baseKey(seg) {
    var n = norm(seg);
    return n ? n.split(' ').map(plural).join(' ') : '';
  }
  function uid() { return Math.random().toString(36).slice(2, 10) + Date.now().toString(36); }
  function addDays(dk, n) { var d = parseISO(dk); d.setDate(d.getDate() + n); return iso(d); }

  /* ---------- persistence ---------- */
  function load() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (raw) {
        var o = JSON.parse(raw);
        state.settings = Object.assign({}, DEFAULT_SETTINGS, o.settings || {});
        state.days = o.days || {};
      }
    } catch (e) { /* ignore corrupt storage */ }
    if (!state.settings) state.settings = Object.assign({}, DEFAULT_SETTINGS);
  }
  function save() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({ settings: state.settings, days: state.days }));
    } catch (e) { /* storage full / private mode */ }
  }

  /* ---------- model ---------- */
  function getMeal(dateKey, meal, create) {
    var d = state.days[dateKey];
    if (!d && create) { d = {}; MEALS.forEach(function (m) { d[m] = []; }); state.days[dateKey] = d; }
    if (!d) return [];
    if (!d[meal] && create) d[meal] = [];
    return d[meal] || [];
  }
  function dayItems(dateKey) {
    var d = state.days[dateKey];
    if (!d) return [];
    var out = [];
    MEALS.forEach(function (m) { (d[m] || []).forEach(function (it) { out.push(it); }); });
    return out;
  }
  function totals(items) {
    var t = { k: 0, p: 0, cb: 0, f: 0 };
    items.forEach(function (it) {
      var f = it.g / 100;
      t.k += it.k * f; t.p += it.p * f; t.cb += it.cb * f; t.f += it.f * f;
    });
    return t;
  }
  function targets() {
    var s = state.settings;
    var bmr = 10 * s.weightKg + 6.25 * s.heightCm - 5 * s.age + (s.sex === 'male' ? 5 : -161);
    var tdee = bmr * s.activity;
    var delta = s.goal === 'lose' ? -500 : (s.goal === 'gain' ? 300 : 0);
    var kcal = Math.max(1200, Math.round((tdee + delta) / 10) * 10);
    var protein = Math.round(s.proteinPerKg * s.weightKg);
    var fat = Math.round(kcal * s.fatPct / 100 / 9);
    var carbs = Math.max(0, Math.round((kcal - protein * 4 - fat * 9) / 4));
    return { kcal: kcal, protein: protein, carbs: carbs, fat: fat, tdee: Math.round(tdee) };
  }

  /* ---------- db load ---------- */
  function loadDB() {
    return fetch(DB_URL, { cache: 'default' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (arr) {
        DB = arr.map(function (o) {
          return {
            n: o.n, u: o.u, c: o.c, k: +o.k || 0,
            p: o.p == null ? 0 : +o.p,
            cb: o.cb == null ? 0 : +o.cb,
            f: o.f == null ? 0 : +o.f,
            pop: o.pop == null ? 0 : +o.pop,
            sv: o.sv || null
          };
        });
        NORM = DB.map(function (o) { return norm(o.n); });
        TOK = DB.map(function (o) { return norm(o.n).split(' ').filter(Boolean); });
        SEG = DB.map(function (o) { return o.n.split(',').map(baseKey); });
        var seen = {};
        DB.forEach(function (o) { if (o.c && !seen[o.c]) { seen[o.c] = 1; CATS.push(o.c); } });
        CATS.sort();
        ready = true;
        fillCategorySelects();
        render();
      });
  }

  // Ranked search: every query word must prefix-match a word in the food name
  // (so "apple" finds "Apples" but not "pineapple"), then results are scored so
  // simple generic foods ("Milk, whole") beat long/branded/processed entries.
  function searchDB(q, cat, limit) {
    var qs = q ? norm(q).split(' ').filter(Boolean) : [];
    var qn = q ? baseKey(q) : '';
    var out = [];
    for (var i = 0; i < DB.length; i++) {
      var o = DB[i];
      if (cat && o.c !== cat) continue;
      if (!qs.length) { out.push({ o: o, s: 0 }); continue; }
      var toks = TOK[i];
      var score = 0, ok = true;
      for (var w = 0; w < qs.length; w++) {
        var word = qs[w];
        var found = -1;
        for (var t = 0; t < toks.length; t++) {
          if (toks[t].indexOf(word) === 0) { found = t; break; }
        }
        if (found === -1) { ok = false; break; }
        score += found === 0 ? 10 : (found === 1 ? 5 : 1);
        var tk = toks[found];
        if (tk === word || tk === word + 's' || tk === word + 'es') score += 4;
        score -= 1.5 * (tk.length - word.length);
        score -= found;
      }
      if (!ok) continue;
      var segs = SEG[i];
      if (segs.length && segs[0] === qn) score += 14;
      else if (segs.length > 1 && segs[1] === qn) score += 9;
      score += o.pop;
      score -= 0.04 * o.n.length;
      out.push({ o: o, s: score });
    }
    if (qs.length) {
      out.sort(function (a, b) {
        return b.s - a.s || a.o.n.length - b.o.n.length ||
          (a.o.n.toLowerCase() < b.o.n.toLowerCase() ? -1 : 1);
      });
    }
    var res = [];
    for (var k = 0; k < out.length && res.length < limit; k++) res.push(out[k].o);
    return res;
  }

  /* ---------- view switching ---------- */
  function showView(v) {
    $$('.view').forEach(function (el) { el.classList.add('hidden'); });
    var el = $('#view-' + v);
    if (el) el.classList.remove('hidden');
    $$('.tab').forEach(function (t) { t.classList.toggle('active', t.dataset.view === v); });
    render();
  }

  function render() {
    if (!ready) return;
    var v = (($('.tab.active') || {}).dataset || {}).view || 'today';
    if (v === 'today') renderToday();
    else if (v === 'week') renderWeek();
    else if (v === 'goals') renderGoals();
    else if (v === 'foods') renderFoods();
  }

  /* ---------- TODAY ---------- */
  function renderToday() {
    $('#dateInput').value = currentDate;
    var label = currentDate === todayISO() ? 'Today'
      : (currentDate === addDays(todayISO(), -1) ? 'Yesterday' : '');
    $('#dayLabel').textContent = label;

    updateSummary(currentDate);

    var host = $('#meals');
    host.innerHTML = MEALS.map(function (meal) {
      var items = getMeal(currentDate, meal, false);
      var tk = totals(items).k;
      var rows = items.length ? items.map(itemRowHTML.bind(null, meal)).join('')
        : '<li class="empty">Nothing logged yet.</li>';
      return '' +
        '<section class="meal">' +
        '<div class="meal-head">' +
        '<h3>' + esc(meal) + '</h3>' +
        '<div class="inline">' +
        '<span class="meal-kcal">' + r0(tk) + ' kcal</span>' +
        '<button class="add" type="button" data-add="' + esc(meal) + '">+ Add food</button>' +
        '</div>' +
        '</div>' +
        '<ul class="meal-items">' + rows + '</ul>' +
        '</section>';
    }).join('');
  }

  function itemRowHTML(meal, it) {
    var f = it.g / 100;
    return '' +
      '<li class="foodrow" data-id="' + esc(it.id) + '" data-meal="' + esc(meal) + '">' +
      '<div class="fr-main">' +
      '<div class="fr-name">' + esc(it.n) + '</div>' +
      '<div class="fr-sub">P ' + r1(it.p * f) + 'g \u00b7 C ' + r1(it.cb * f) + 'g \u00b7 F ' + r1(it.f * f) + 'g</div>' +
      '</div>' +
      '<input class="grams" type="number" min="0" step="1" inputmode="decimal" value="' + it.g + '" aria-label="Grams">' +
      '<div class="kcal">' + r0(it.k * f) + '</div>' +
      '<button class="x" type="button" aria-label="Remove">&times;</button>' +
      '</li>';
  }

  function updateSummary(dateKey) {
    var t = totals(dayItems(dateKey));
    var g = targets();
    $('#kcalEaten').textContent = r0(t.k);
    $('#kcalTarget').textContent = g.kcal;
    var pct = g.kcal ? (t.k / g.kcal) * 100 : 0;
    var bar = $('#kcalBar');
    bar.style.width = Math.min(100, pct) + '%';
    bar.classList.toggle('over', pct > 100);
    var left = g.kcal - t.k;
    $('#kcalLeft').innerHTML = left >= 0
      ? r0(left) + ' kcal left'
      : '<b style="color:var(--danger)">' + r0(-left) + ' kcal over</b>';

    var macros = [
      { lab: 'Protein', v: t.p, goal: g.protein, cls: 'p' },
      { lab: 'Carbs', v: t.cb, goal: g.carbs, cls: 'c' },
      { lab: 'Fat', v: t.f, goal: g.fat, cls: 'f' }
    ];
    $('#macroBars').innerHTML = macros.map(function (m) {
      var p = m.goal ? Math.min(100, (m.v / m.goal) * 100) : 0;
      return '<div class="macro">' +
        '<div class="m-top"><span>' + m.lab + '</span><span>' + r0(m.v) + '/' + r0(m.goal) + 'g</span></div>' +
        '<div class="bar"><i class="' + m.cls + '" style="width:' + p + '%"></i></div>' +
        '</div>';
    }).join('');
  }

  /* ---------- WEEK ---------- */
  function weekDates() {
    var d = parseISO(currentDate);
    var dow = (d.getDay() + 6) % 7; // Mon = 0
    var mon = addDays(currentDate, -dow);
    var out = [];
    for (var i = 0; i < 7; i++) out.push(addDays(mon, i));
    return out;
  }
  function renderWeek() {
    var g = targets();
    var days = weekDates();
    var today = todayISO();
    var tot = { k: 0, p: 0, cb: 0, f: 0 };
    var maxK = g.kcal;
    var rows = days.map(function (dk) {
      var t = totals(dayItems(dk));
      tot.k += t.k; tot.p += t.p; tot.cb += t.cb; tot.f += t.f;
      if (t.k > maxK) maxK = t.k;
      var cls = dk === today ? ' class="today"' : '';
      return '<tr' + cls + '><td>' + parseISO(dk).toLocaleDateString(undefined, { weekday: 'short' }) +
        (dk === today ? ' <span class="muted">(today)</span>' : '') + '</td>' +
        '<td>' + r0(t.k) + '</td><td>' + r0(t.p) + '</td><td>' + r0(t.cb) + '</td><td>' + r0(t.f) + '</td></tr>';
    }).join('');

    $('#weekSummary').innerHTML =
      '<div class="target-grid">' +
      '<div class="target"><div class="t-lab">Weekly calories</div><div class="t-val">' + r0(tot.k) + '</div></div>' +
      '<div class="target"><div class="t-lab">Daily average</div><div class="t-val">' + r0(tot.k / 7) + '</div></div>' +
      '<div class="target"><div class="t-lab">Calorie target</div><div class="t-val">' + g.kcal + '</div></div>' +
      '<div class="target"><div class="t-lab">Days logged</div><div class="t-val">' + days.filter(function (d) { return dayItems(d).length; }).length + '/7</div></div>' +
      '</div>' +
      '<table class="wtable"><thead><tr><th>Day</th><th>kcal</th><th>P g</th><th>C g</th><th>F g</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>';

    $('#weekChart').innerHTML = days.map(function (dk) {
      var t = totals(dayItems(dk));
      var h = maxK ? Math.max(2, (t.k / maxK) * 100) : 2;
      var cls = 'colbar' + (t.k > g.kcal ? ' over' : '') + (dk === today ? ' today' : '');
      return '<div class="col">' +
        '<div class="colval">' + (t.k ? r0(t.k) : '') + '</div>' +
        '<div class="' + cls + '" style="height:' + h + '%"></div>' +
        '<div class="colcap">' + parseISO(dk).toLocaleDateString(undefined, { weekday: 'short' }) + '</div>' +
        '</div>';
    }).join('');
  }

  /* ---------- GOALS ---------- */
  var unitMode = 'metric';

  function renderGoals() {
    var s = state.settings;
    $('#gSex').value = s.sex;
    $('#gAge').value = s.age;
    $('#gHeightCm').value = s.heightCm;
    $('#gWeightKg').value = s.weightKg;
    $('#gActivity').value = String(s.activity);
    $('#gGoal').value = s.goal;
    $('#gProtein').value = s.proteinPerKg;
    $('#gFatPct').value = s.fatPct;
    syncUnitFields();
    renderTargetSummary();
  }

  function syncUnitFields() {
    var s = state.settings;
    var imperial = unitMode === 'imperial';
    $('#heightMetric').classList.toggle('hidden', imperial);
    $('#heightImperial').classList.toggle('hidden', !imperial);
    $('#weightMetric').classList.toggle('hidden', imperial);
    $('#weightImperial').classList.toggle('hidden', !imperial);
    $$('#unitSeg button').forEach(function (b) { b.classList.toggle('active', b.dataset.unit === unitMode); });
    if (imperial) {
      var totalIn = s.heightCm / 2.54;
      var ft = Math.floor(totalIn / 12);
      var inch = Math.round(totalIn - ft * 12);
      if (inch === 12) { ft += 1; inch = 0; }
      $('#gHeightFt').value = ft;
      $('#gHeightIn').value = inch;
      $('#gWeightLb').value = r1(s.weightKg * 2.2046226);
    }
  }

  function readGoalsForm() {
    var s = state.settings;
    s.sex = $('#gSex').value;
    s.age = +$('#gAge').value || s.age;
    if (unitMode === 'imperial') {
      var ft = +$('#gHeightFt').value || 0;
      var inch = +$('#gHeightIn').value || 0;
      s.heightCm = Math.round((ft * 12 + inch) * 2.54 * 10) / 10;
      s.weightKg = Math.round((+$('#gWeightLb').value || 0) / 2.2046226 * 10) / 10;
    } else {
      s.heightCm = +$('#gHeightCm').value || s.heightCm;
      s.weightKg = +$('#gWeightKg').value || s.weightKg;
    }
    s.activity = +$('#gActivity').value || s.activity;
    s.goal = $('#gGoal').value;
    s.proteinPerKg = +$('#gProtein').value || s.proteinPerKg;
    s.fatPct = +$('#gFatPct').value || s.fatPct;
    save();
  }

  function renderTargetSummary() {
    var g = targets();
    var s = state.settings;
    $('#targetSummary').innerHTML =
      '<h2 class="h2">Your daily targets</h2>' +
      '<div class="target-grid">' +
      '<div class="target"><div class="t-lab">Calories</div><div class="t-val">' + g.kcal + '</div></div>' +
      '<div class="target"><div class="t-lab">Protein</div><div class="t-val">' + g.protein + ' g</div></div>' +
      '<div class="target"><div class="t-lab">Carbs</div><div class="t-val">' + g.carbs + ' g</div></div>' +
      '<div class="target"><div class="t-lab">Fat</div><div class="t-val">' + g.fat + ' g</div></div>' +
      '</div>' +
      '<p class="muted small" style="margin:12px 0 0">Estimated maintenance is about <b>' + g.tdee +
      '</b> kcal/day (Mifflin-St Jeor). Targets are estimates, not medical advice.</p>';
  }

  /* ---------- FOODS (browse) ---------- */
  function fillCategorySelects() {
    var opts = '<option value="">All categories</option>' + CATS.map(function (c) {
      return '<option value="' + esc(c) + '">' + esc(c) + '</option>';
    }).join('');
    $('#browseCat').innerHTML = opts;
    $('#pickerCat').innerHTML = opts;
  }

  function foodRowHTML(o) {
    var serving = '';
    if (o.sv && o.sv.length) {
      var s0 = o.sv[0];
      if (s0.g && s0.g > 0) serving = ' \u00b7 1 ' + esc(s0.d) + ' \u2248 ' + r0(s0.g) + 'g';
    }
    return '<div class="foodrow" data-name="' + esc(o.n) + '">' +
      '<div class="fr-main">' +
      '<div class="fr-name">' + esc(o.n) + '</div>' +
      '<div class="fr-sub">' + r0(o.k) + ' kcal \u00b7 P ' + r1(o.p) + ' \u00b7 C ' + r1(o.cb) + ' \u00b7 F ' + r1(o.f) + ' /100g' + serving + '</div>' +
      '</div>' +
      '</div>';
  }

  function renderFoods() {
    var q = $('#browseSearch').value;
    var cat = $('#browseCat').value;
    var results = searchDB(q, cat, 60);
    var host = $('#browseResults');
    if (!q && !cat) {
      host.innerHTML = '<div class="morepad">Search above to browse all ' + DB.length.toLocaleString() +
        ' foods, or pick a category.</div>';
      return;
    }
    if (!results.length) { host.innerHTML = '<div class="morepad">No foods match that search.</div>'; return; }
    host.innerHTML = results.map(foodRowHTML).join('') +
      (results.length >= 60 ? '<div class="morepad">Showing first 60 \u2014 keep typing to narrow.</div>' : '');
    $('#foodCount').textContent = DB.length.toLocaleString();
  }

  /* ---------- PICKER MODAL ---------- */
  var pickerMeal = null;
  var pickedFood = null;

  function openPicker(meal) {
    if (!ready) return;
    pickerMeal = meal;
    pickedFood = null;
    $('#modalTitle').textContent = 'Add to ' + meal;
    $('#pickerSearch').value = '';
    $('#pickerCat').value = '';
    $('#picked').classList.add('hidden');
    $('#picked').innerHTML = '';
    renderPicker();
    $('#modal').classList.remove('hidden');
    setTimeout(function () { $('#pickerSearch').focus(); }, 30);
  }
  function closePicker() { $('#modal').classList.add('hidden'); }

  function renderPicker() {
    var q = $('#pickerSearch').value;
    var cat = $('#pickerCat').value;
    var host = $('#pickerResults');
    if (!q && !cat) {
      host.innerHTML = '<div class="morepad">Type to search ' + DB.length.toLocaleString() +
        ' foods by name (e.g. \u201cchicken breast\u201d), or choose a category.</div>';
      return;
    }
    var results = searchDB(q, cat, 60);
    if (!results.length) { host.innerHTML = '<div class="morepad">No foods match that search.</div>'; return; }
    host.innerHTML = results.map(foodRowHTML).join('') +
      (results.length >= 60 ? '<div class="morepad">Showing first 60 \u2014 keep typing to narrow.</div>' : '');
  }

  function pickFood(name) {
    pickedFood = DB.find(function (o) { return o.n === name; });
    if (!pickedFood) return;
    var defG = (pickedFood.sv && pickedFood.sv[0] && pickedFood.sv[0].g) ? r0(pickedFood.sv[0].g) : 100;
    var chips = (pickedFood.sv || []).filter(function (s) { return s.g > 0; }).map(function (s) {
      return '<button class="chip" type="button" data-serving="' + s.g + '">1 ' + esc(s.d) + ' (' + r0(s.g) + 'g)</button>';
    }).join('');
    $('#picked').innerHTML =
      '<div class="pk-name">' + esc(pickedFood.n) + '</div>' +
      '<div class="muted small">' + r0(pickedFood.k) + ' kcal \u00b7 P ' + r1(pickedFood.p) + ' \u00b7 C ' + r1(pickedFood.cb) + ' \u00b7 F ' + r1(pickedFood.f) + ' per 100g</div>' +
      '<div class="pk-controls">' +
      '<span class="small muted">Amount (g)</span>' +
      '<input class="pk-grams" type="number" min="0" step="1" inputmode="decimal" value="' + defG + '">' +
      (chips ? '<span class="small muted">or</span>' + chips : '') +
      '<button class="btn" type="button" id="confirmAdd">Add to ' + esc(pickerMeal) + '</button>' +
      '</div>';
    $('#picked').classList.remove('hidden');
  }

  function confirmAdd() {
    if (!pickedFood) return;
    var g = +$('.pk-grams').value || 0;
    if (g <= 0) { $('.pk-grams').focus(); return; }
    var list = getMeal(currentDate, pickerMeal, true);
    list.push({
      id: uid(), n: pickedFood.n, g: g,
      k: pickedFood.k, p: pickedFood.p, cb: pickedFood.cb, f: pickedFood.f
    });
    save();
    closePicker();
    renderToday();
  }

  /* ---------- EXPORT / RESET ---------- */
  function exportCSV() {
    var lines = ['date,meal,food,grams,kcal,protein_g,carbs_g,fat_g'];
    Object.keys(state.days).sort().forEach(function (dk) {
      var d = state.days[dk];
      MEALS.forEach(function (m) {
        (d[m] || []).forEach(function (it) {
          var f = it.g / 100;
          lines.push([dk, m, '"' + it.n.replace(/"/g, '""') + '"', it.g,
            r0(it.k * f), r1(it.p * f), r1(it.cb * f), r1(it.f * f)].join(','));
        });
      });
    });
    var blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'calorie-tracker-log.csv';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  function resetAll() {
    if (!confirm('Delete all logged foods and reset your goals? This cannot be undone.')) return;
    try { localStorage.removeItem(LS_KEY); } catch (e) { }
    state.days = {};
    state.settings = Object.assign({}, DEFAULT_SETTINGS);
    currentDate = todayISO();
    save();
    renderGoals();
  }

  /* ---------- events ---------- */
  function bind() {
    $('#tabs').addEventListener('click', function (e) {
      var b = e.target.closest('.tab');
      if (b) showView(b.dataset.view);
    });

    $('#prevDay').addEventListener('click', function () { currentDate = addDays(currentDate, -1); renderToday(); });
    $('#nextDay').addEventListener('click', function () { currentDate = addDays(currentDate, 1); renderToday(); });
    $('#dateInput').addEventListener('change', function () { if (this.value) { currentDate = this.value; renderToday(); } });

    $('#meals').addEventListener('click', function (e) {
      var addBtn = e.target.closest('[data-add]');
      if (addBtn) { openPicker(addBtn.dataset.add); return; }
      var x = e.target.closest('.x');
      if (x) {
        var row = x.closest('.foodrow');
        var meal = row.dataset.meal, id = row.dataset.id;
        var list = getMeal(currentDate, meal, false);
        var idx = list.findIndex(function (it) { return it.id === id; });
        if (idx >= 0) { list.splice(idx, 1); save(); renderToday(); }
      }
    });
    $('#meals').addEventListener('change', function (e) {
      var inp = e.target.closest('input.grams');
      if (!inp) return;
      var row = inp.closest('.foodrow');
      var meal = row.dataset.meal, id = row.dataset.id;
      var list = getMeal(currentDate, meal, false);
      var it = list.find(function (o) { return o.id === id; });
      if (it) { it.g = Math.max(0, +inp.value || 0); save(); renderToday(); }
    });

    // modal
    $('#modalClose').addEventListener('click', closePicker);
    $('#modal').addEventListener('click', function (e) { if (e.target === $('#modal')) closePicker(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closePicker(); });
    $('#pickerSearch').addEventListener('input', renderPicker);
    $('#pickerCat').addEventListener('change', renderPicker);
    $('#pickerResults').addEventListener('click', function (e) {
      var row = e.target.closest('.foodrow');
      if (row && row.dataset.name) pickFood(row.dataset.name);
    });
    $('#picked').addEventListener('click', function (e) {
      var chip = e.target.closest('[data-serving]');
      if (chip) { $('.pk-grams').value = chip.dataset.serving; }
      if (e.target.closest('#confirmAdd')) confirmAdd();
    });

    // browse
    $('#browseSearch').addEventListener('input', renderFoods);
    $('#browseCat').addEventListener('change', renderFoods);

    // goals
    $$('#unitSeg button').forEach(function (b) {
      b.addEventListener('click', function () {
        unitMode = b.dataset.unit;
        syncUnitFields();
      });
    });
    $('#goalsForm').addEventListener('submit', function (e) {
      e.preventDefault();
      readGoalsForm();
      renderGoals();
      var msg = $('#goalsSaved');
      msg.textContent = 'Saved.';
      setTimeout(function () { msg.textContent = ''; }, 1500);
    });
    $('#exportCsv').addEventListener('click', exportCSV);
    $('#resetAll').addEventListener('click', resetAll);
  }

  /* ---------- boot ---------- */
  load();
  bind();
  loadDB().catch(function (err) {
    $('#meals').innerHTML = '<section class="card"><p class="muted">Could not load the food database (' +
      esc(err.message) + '). Check your connection and reload.</p></section>';
  });

  // Register the service worker for offline support / installability.
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('sw.js').catch(function () { });
    });
  }
})();
