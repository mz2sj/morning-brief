(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var danger = style.getPropertyValue('--danger').trim();

  var D = window.ROLL_IC;
  var dates = D.dates;
  var N = dates.length;

  function line(name, data, color, opts) {
    opts = opts || {};
    return {
      name: name, type: 'line', data: data, symbol: 'none', z: opts.z || 3,
      lineStyle: { width: opts.width || 2, type: opts.dash ? 'dashed' : 'solid', color: color, opacity: opts.opacity || 1 },
      itemStyle: { color: color },
      emphasis: { focus: 'series' },
      connectNulls: false
    };
  }

  function dividendSeasonAreas() {
    var areas = [], runStart = null, prev = null;
    for (var i = 0; i < N; i++) {
      var m = parseInt(dates[i].slice(5, 7), 10);
      var inSeason = (m >= 5 && m <= 7);
      if (inSeason && runStart === null) runStart = i;
      if ((!inSeason || i === N - 1) && runStart !== null) {
        var runEnd = (!inSeason) ? prev : i;
        areas.push([{ xAxis: dates[runStart], itemStyle: { color: '#8a8a9a', opacity: 0.09 }, label: { show: runEnd - runStart > 6, position: 'insideTop', color: muted, fontSize: 11 } }, { xAxis: dates[runEnd] }]);
        runStart = null;
      }
      prev = i;
    }
    return areas;
  }
  var seasonAreas = dividendSeasonAreas();

  function baseAxis() {
    return {
      type: 'category', data: dates, boundaryGap: false,
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false },
      axisLabel: { color: muted, fontSize: 11, fontFamily: 'GeistMono' }
    };
  }

  // ---------- Hero: 贴水年化 ----------
  var chartDiscount = echarts.init(document.getElementById('chart-discount'), null, { renderer: 'svg' });
  chartDiscount.setOption({
    animation: false,
    grid: { left: 8, right: 14, top: 42, bottom: 74, containLabel: true },
    legend: {
      top: 4, textStyle: { color: ink, fontSize: 12 }, itemWidth: 22,
      selected: { '当月': false, '下月': false },
      data: ['当月', '下月', '季月', '次季', '季月·表面', '次季·表面']
    },
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function (v) { return v == null ? '-' : v.toFixed(2) + '%'; } },
    xAxis: baseAxis(),
    yAxis: {
      type: 'value', axisLabel: { formatter: '{value}%', color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule } }
    },
    dataZoom: [
      { type: 'inside' },
      { type: 'slider', height: 16, bottom: 10, borderColor: rule, fillerColor: 'rgba(75,63,227,0.12)', handleStyle: { color: accent }, textStyle: { color: muted, fontSize: 10 } }
    ],
    series: [
      line('当月', D.slots['当月'].net, muted, { width: 1.5, opacity: 0.85 }),
      line('下月', D.slots['下月'].net, '#9a9aa8', { width: 1.5, opacity: 0.9 }),
      line('季月', D.slots['季月'].net, accent, { width: 2.5, z: 5 }),
      line('次季', D.slots['次季'].net, accent2, { width: 2.5, z: 5 }),
      line('季月·表面', D.slots['季月'].gross, accent, { dash: true, width: 2, opacity: 0.8, z: 2 }),
      line('次季·表面', D.slots['次季'].gross, accent2, { dash: true, width: 2, opacity: 0.8, z: 2 }),
      {
        type: 'line', markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: accent2, type: 'dashed', width: 1.5 },
          label: { formatter: '贴水参考 10%', color: accent2, fontSize: 11, position: 'insideEndTop' },
          data: [{ yAxis: 10 }]
        }, data: []
      },
      { type: 'line', markArea: { silent: true, data: seasonAreas }, data: [] }
    ]
  });

  // ---------- 分红侵蚀 ----------
  var chartErosion = echarts.init(document.getElementById('chart-erosion'), null, { renderer: 'svg' });
  chartErosion.setOption({
    animation: false,
    grid: { left: 8, right: 14, top: 34, bottom: 12, containLabel: true },
    legend: { top: 4, textStyle: { color: ink, fontSize: 12 }, itemWidth: 22, data: ['季月', '次季'] },
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function (v) { return v == null ? '-' : v.toFixed(2) + 'pp'; } },
    xAxis: baseAxis(),
    yAxis: {
      type: 'value', axisLabel: { formatter: '{value}pp', color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule } }
    },
    dataZoom: [{ type: 'inside' }],
    series: [
      line('季月', D.slots['季月'].erosion, accent, { width: 2 }),
      line('次季', D.slots['次季'].erosion, accent2, { width: 2 }),
      {
        type: 'line', markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: danger, type: 'dashed', width: 1.5 },
          label: { formatter: '告警 1.5pp', color: danger, fontSize: 11 },
          data: [{ yAxis: 1.5 }]
        }, data: []
      },
      { type: 'line', markArea: { silent: true, data: seasonAreas }, data: [] }
    ]
  });

  // ---------- 估值分位 ----------
  var chartPctile = echarts.init(document.getElementById('chart-pctile'), null, { renderer: 'svg' });
  chartPctile.setOption({
    animation: false,
    grid: { left: 8, right: 14, top: 34, bottom: 12, containLabel: true },
    legend: { top: 4, textStyle: { color: ink, fontSize: 12 }, itemWidth: 22, data: ['近10年', '近5年'] },
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function (v) { return v == null ? '-' : v.toFixed(1) + '%'; } },
    xAxis: baseAxis(),
    yAxis: {
      type: 'value', min: 0, max: 100,
      axisLabel: { formatter: '{value}%', color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule } }
    },
    dataZoom: [{ type: 'inside' }],
    series: [
      line('近10年', D.pct10, accent, { width: 2.5 }),
      line('近5年', D.pct5, muted, { width: 1.5 }),
      {
        type: 'line', markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: accent2, type: 'dashed', width: 1.5 },
          label: { formatter: '买点线 20%', color: accent2, fontSize: 11, position: 'insideEndTop' },
          data: [{ yAxis: 20 }]
        }, data: []
      },
      {
        type: 'line', markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: danger, type: 'dashed', width: 1.5 },
          label: { formatter: '劝退线 90%', color: danger, fontSize: 11, position: 'insideEndBottom' },
          data: [{ yAxis: 90 }]
        }, data: []
      }
    ]
  });

  // ---------- 指数走势 ----------
  var chartIndex = echarts.init(document.getElementById('chart-index'), null, { renderer: 'svg' });
  chartIndex.setOption({
    animation: false,
    grid: { left: 8, right: 14, top: 18, bottom: 12, containLabel: true },
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function (v) { return v == null ? '-' : v.toLocaleString(); } },
    xAxis: baseAxis(),
    yAxis: {
      type: 'value', scale: true,
      axisLabel: { color: muted, fontSize: 11, fontFamily: 'GeistMono' },
      splitLine: { lineStyle: { color: rule } }
    },
    dataZoom: [{ type: 'inside' }],
    series: [line('中证500', D.idxClose, accent, { width: 2 })]
  });

  // ---------- 联动与时间筛选 ----------
  var charts = [chartDiscount, chartErosion, chartPctile, chartIndex];
  charts.forEach(function (c) { c.group = 'rollic'; });
  echarts.connect('rollic');
  window.addEventListener('resize', function () { charts.forEach(function (c) { c.resize(); }); });

  document.getElementById('filterbar').addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-days]');
    if (!btn) return;
    var days = parseInt(btn.dataset.days, 10);
    var startPct = days > 0 ? Math.max(0, (N - days) / N * 100) : 0;
    chartDiscount.dispatchAction({ type: 'dataZoom', start: startPct, end: 100 });
    document.querySelectorAll('#filterbar button').forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');
  });

  // ---------- KPI / 徽标 / 表格 ----------
  var lastIdx = N - 1;
  var lastWith = function (arr) { for (var i = lastIdx; i >= 0; i--) { if (arr[i] != null) return { v: arr[i], i: i }; } return null; };

  var closeLast = lastWith(D.idxClose);
  document.getElementById('kpi-index').textContent = closeLast.v.toLocaleString();
  document.getElementById('kpi-pe').textContent = 'PE-TTM ' + D.pe[closeLast.i] + ' · ' + dates[closeLast.i];

  var pct10Last = lastWith(D.pct10);
  document.getElementById('kpi-pct').textContent = pct10Last.v.toFixed(1) + '%';
  document.getElementById('kpi-pct').parentElement.querySelector('.hint').textContent = '近5年分位 ' + lastWith(D.pct5).v.toFixed(1) + '% · <20%舒服 / ≥90%劝退';

  var farRow = D.latest.filter(function (r) { return r.label === '次季' && !r.empty; })[0];
  if (farRow) {
    document.getElementById('kpi-net').textContent = farRow.net.toFixed(2) + '%';
    document.getElementById('kpi-net-sub').textContent = '表面 ' + farRow.gross.toFixed(2) + '% − 虚胖 ' + farRow.erosion.toFixed(2) + 'pp · ' + farRow.code;
  }

  var eroPeak = Math.max.apply(null, D.slots['次季'].erosion.filter(function (v) { return v != null; }));
  document.getElementById('kpi-ero').textContent = eroPeak.toFixed(2) + 'pp';

  var badge = document.getElementById('signal-badge');
  badge.textContent = D.meta.tier.text;
  if (D.meta.tier.level === 'green') badge.classList.add('ok');
  else if (D.meta.tier.level === 'red') badge.classList.add('warn');

  document.getElementById('gen-date').textContent = '数据截至 ' + D.meta.dataRange[1] + ' · 生成于 ' + D.meta.generated;
  document.getElementById('div-rate').textContent = D.meta.annualDividend + '%';
  document.getElementById('snap-desc').textContent = '四张在市合约的最新读数，点击任意行可展开该合约的完整年化计算过程。基差门槛（作者口径）：近月≥' + D.meta.thresholds.basisNear + '点、季月≥' + D.meta.thresholds.basisFar + '点才值得滚；"下月"若为刚挂牌的新合约，行情生成前显示为"—"。';

  var tbody = document.getElementById('snap-body');
  D.latest.forEach(function (r) {
    var tr = document.createElement('tr');
    tr.className = 'main-row';
    if (r.empty) {
      tr.innerHTML = '<td>' + r.code + '</td><td>' + r.label + '</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>新挂牌无行情</td>';
    } else {
      var status;
      if (r.alert) status = '<td class="neg">⚠ 跨分红季</td>';
      else if (r.worth) status = '<td class="pos">✓ 值得滚</td>';
      else status = '<td class="neg">贴水偏薄</td>';
      var ptsTd = '<td>' + r.idx.toFixed(2) + '<span style="color:var(--muted)"> / </span>' + r.fut.toFixed(2) + '</td>';
      var basisTd = '<td>' + r.basis.toFixed(0) + '点<span style="color:var(--muted)">/' + r.basisTh + '</span></td>';
      var eroTd = r.erosion >= D.meta.thresholds.erosionAlert ? '<td class="neg">' + r.erosion.toFixed(2) + 'pp</td>' : '<td>' + r.erosion.toFixed(2) + 'pp</td>';
      tr.innerHTML = '<td>' + r.code + '</td><td>' + r.label + '</td><td>' + r.expiry + '</td><td>' + r.days + '</td>' +
        ptsTd + basisTd + '<td>' + r.gross.toFixed(2) + '%</td>' + eroTd + '<td>' + r.net.toFixed(2) + '%</td>' + status;
    }
    tbody.appendChild(tr);
    if (r.empty) return;

    var basis = r.idx - r.fut;
    var rate = basis / r.idx * 100;
    var factor = 365 / r.days;
    var gross = rate * factor;
    var divFrac = r.erosion * r.days / 365;
    var detail = document.createElement('tr');
    detail.className = 'detail-row';
    detail.style.display = 'none';
    detail.innerHTML = '<td colspan="10">' +
      '<span class="step">① 基差 <span class="op">= 指数 − 期货 =</span> ' + r.idx.toFixed(2) + ' − ' + r.fut.toFixed(2) + ' <span class="op">=</span> <b>' + basis.toFixed(1) + ' 点</b></span>' +
      '<span class="step">② 贴水率 <span class="op">= 基差 ÷ 指数 =</span> ' + basis.toFixed(1) + ' ÷ ' + r.idx.toFixed(2) + ' <span class="op">=</span> <b>' + rate.toFixed(3) + '%</b></span>' +
      '<span class="step">③ 年化因子 <span class="op">= 365 ÷ 剩余天数 =</span> 365 ÷ ' + r.days + ' <span class="op">=</span> <b>' + factor.toFixed(3) + '</b></span>' +
      '<span class="step">④ 表面年化 <span class="op">= 贴水率 × 年化因子 =</span> ' + rate.toFixed(3) + '% × ' + factor.toFixed(3) + ' <span class="op">=</span> <b>' + gross.toFixed(2) + '%</b></span>' +
      '<span class="step">⑤ 窗口预期分红 <span class="op">≈</span> ' + divFrac.toFixed(3) + '%<span class="op">，折年化虚胖</span> <b>' + r.erosion.toFixed(2) + 'pp</b></span>' +
      '<span class="step">⑥ 真实年化 <span class="op">= 表面年化 − 分红虚胖 =</span> ' + gross.toFixed(2) + '% − ' + r.erosion.toFixed(2) + 'pp <span class="op">=</span> <b>' + r.net.toFixed(2) + '%</b></span>' +
      '<span class="dateline">数据日期 ' + r.date + ' · 到期日 ' + r.expiry + '（剩 ' + r.days + ' 天）</span>' +
      '</td>';
    tr.addEventListener('click', function () {
      detail.style.display = detail.style.display === 'none' ? '' : 'none';
    });
    tbody.appendChild(detail);
  });
})();
