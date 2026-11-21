// assets/charts.js — OpenMinis analysis report charts
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart: language composition (horizontal bar) ---
  var el = document.getElementById('chart-lang');
  if (el && window.echarts) {
    var chart = echarts.init(el, null, { renderer: 'svg' });
    var cats = [
      'C/C++ · Android JNI',
      'Shell · 构建脚本',
      'Objective-C · iOS 桥',
      'Swift · iOS App',
      'Kotlin · Android App'
    ];
    var vals = [3, 13, 85, 1040, 1497];
    var colors = [muted, muted, accent2, accent, accent2];
    chart.setOption({
      animation: false,
      tooltip: {
        trigger: 'item',
        appendToBody: true,
        formatter: function(p) { return p.name + '：' + p.value + ' 个文件'; }
      },
      grid: { left: 200, right: 70, top: 24, bottom: 30 },
      xAxis: {
        type: 'value',
        name: '文件数',
        nameTextStyle: { color: muted, fontSize: 12 },
        axisLabel: { color: muted },
        splitLine: { lineStyle: { color: rule } },
        axisLine: { show: false }
      },
      yAxis: {
        type: 'category',
        data: cats,
        axisLabel: { color: ink, fontSize: 13, fontFamily: 'JetBrainsMono, monospace' },
        axisLine: { lineStyle: { color: rule } },
        axisTick: { show: false }
      },
      series: [{
        type: 'bar',
        data: vals.map(function(v, i) {
          return { value: v, itemStyle: { color: colors[i], borderRadius: [0, 4, 4, 0] } };
        }),
        barWidth: 26,
        label: {
          show: true,
          position: 'right',
          color: ink,
          fontWeight: 700,
          fontFamily: 'JetBrainsMono, monospace',
          formatter: '{c}'
        }
      }]
    });
    window.addEventListener('resize', function() { chart.resize(); });
  }
})();
