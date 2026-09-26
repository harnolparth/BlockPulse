/* Minimal canvas chart helpers — no CDN dependency, works fully offline. */

const CHART_FONT = "Segoe UI, -apple-system, Roboto, Arial, sans-serif";

function fitCanvas(canvas){
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  return {ctx, w: rect.width, h: rect.height};
}

function emptyState(ctx, w, h, msg){
  ctx.fillStyle = "#7C877E"; ctx.font = "13px " + CHART_FONT;
  ctx.fillText(msg || "Not enough data yet", 14, h/2);
}

/**
 * drawLineChart(canvas, series, opts)
 * `series` may be either:
 *   - a flat array of points [{t,v}, ...]                (single line, back-compat)
 *   - an array of named series [{name, color, points:[{t,v}]}, ...]  (multi-line + legend)
 */
function drawLineChart(canvas, series, opts={}){
  if(!canvas) return;
  const {ctx, w, h} = fitCanvas(canvas);
  ctx.clearRect(0,0,w,h);

  const multi = Array.isArray(series) && series.length && series[0] && Array.isArray(series[0].points);
  const lines = multi ? series : [{name: opts.name, color: opts.color || "#3E8D5C", points: series, fill: true}];
  const hasLegend = multi && lines.length > 1;

  const pad = {top:14, right:14, bottom:22, left:36};
  if(hasLegend) pad.top += 18;
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;

  const allValues = lines.flatMap(l => l.points.map(p => p.v)).filter(v => v !== null && v !== undefined);
  if(allValues.length < 2){ emptyState(ctx, w, h); return; }

  const min = opts.min !== undefined ? opts.min : Math.min(...allValues, opts.threshold ?? Infinity) - 1;
  const max = opts.max !== undefined ? opts.max : Math.max(...allValues, opts.threshold ?? -Infinity) + 1;
  const range = (max - min) || 1;

  // gridlines
  ctx.strokeStyle = "#E9E4D6"; ctx.lineWidth = 1;
  for(let i=0;i<=3;i++){
    const y = pad.top + plotH*(i/3);
    ctx.beginPath(); ctx.moveTo(pad.left,y); ctx.lineTo(w-pad.right,y); ctx.stroke();
    ctx.fillStyle = "#7C877E"; ctx.font = "10px " + CHART_FONT;
    ctx.fillText(Math.round(max - range*(i/3)), 2, y+3);
  }
  if(opts.threshold !== undefined){
    const ty = pad.top + plotH * (1 - (opts.threshold - min)/range);
    ctx.strokeStyle = "#B23B34"; ctx.setLineDash([4,3]); ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.moveTo(pad.left,ty); ctx.lineTo(w-pad.right,ty); ctx.stroke();
    ctx.setLineDash([]);
    if(opts.thresholdLabel){
      ctx.fillStyle = "#B23B34"; ctx.font = "10px " + CHART_FONT;
      ctx.fillText(opts.thresholdLabel, w - pad.right - ctx.measureText(opts.thresholdLabel).width, ty - 4);
    }
  }

  lines.forEach(line => {
    const validPts = line.points.filter(p => p.v !== null && p.v !== undefined);
    if(validPts.length < 2) return;
    const pts = line.points.map((p,i) => ({
      x: pad.left + plotW * (i/(line.points.length-1)),
      y: pad.top + plotH * (1 - ((p.v ?? min) - min)/range),
      has: p.v !== null && p.v !== undefined,
    }));

    if(line.fill !== false && !hasLegend){
      const grad = ctx.createLinearGradient(0,pad.top,0,pad.top+plotH);
      grad.addColorStop(0, hexToRgba(line.color, 0.22));
      grad.addColorStop(1, hexToRgba(line.color, 0.02));
      ctx.beginPath();
      let started = false;
      pts.forEach(p => { if(p.has){ if(!started){ ctx.moveTo(p.x, pad.top+plotH); ctx.lineTo(p.x,p.y); started=true; } else ctx.lineTo(p.x,p.y); } });
      const lastPt = [...pts].reverse().find(p=>p.has);
      if(lastPt) ctx.lineTo(lastPt.x, pad.top+plotH);
      ctx.closePath();
      ctx.fillStyle = grad; ctx.fill();
    }

    ctx.beginPath();
    ctx.strokeStyle = line.color; ctx.lineWidth = 2.2; ctx.lineJoin = "round";
    let moved = false;
    pts.forEach(p => { if(p.has){ if(!moved){ ctx.moveTo(p.x,p.y); moved=true; } else ctx.lineTo(p.x,p.y); } });
    ctx.stroke();

    ctx.fillStyle = line.color;
    const last = [...pts].reverse().find(p=>p.has);
    if(last){ ctx.beginPath(); ctx.arc(last.x, last.y, 3.5, 0, Math.PI*2); ctx.fill(); }
  });

  if(hasLegend){
    let lx = pad.left;
    ctx.font = "11px " + CHART_FONT;
    lines.forEach(line => {
      ctx.fillStyle = line.color;
      ctx.fillRect(lx, 2, 9, 9);
      ctx.fillStyle = "#4B554D";
      ctx.fillText(line.name, lx + 13, 10);
      lx += 13 + ctx.measureText(line.name).width + 16;
    });
  }
}

function hexToRgba(hex, alpha){
  if(!hex || hex[0] !== "#") return `rgba(63,141,92,${alpha})`;
  const v = hex.length === 4
    ? [hex[1]+hex[1], hex[2]+hex[2], hex[3]+hex[3]]
    : [hex.slice(1,3), hex.slice(3,5), hex.slice(5,7)];
  const [r,g,b] = v.map(x => parseInt(x,16));
  return `rgba(${r},${g},${b},${alpha})`;
}

function drawDonut(canvas, segments){
  // segments: [{label, value, color}]
  if(!canvas) return;
  const {ctx, w, h} = fitCanvas(canvas);
  ctx.clearRect(0,0,w,h);
  const total = segments.reduce((a,s)=>a+s.value,0) || 1;
  const cx = w*0.32, cy = h/2, r = Math.min(cx,h/2)-6, rInner = r*0.6;
  let start = -Math.PI/2;
  segments.forEach(seg => {
    const angle = (seg.value/total) * Math.PI*2;
    ctx.beginPath();
    ctx.moveTo(cx,cy);
    ctx.arc(cx,cy,r,start,start+angle);
    ctx.closePath();
    ctx.fillStyle = seg.color;
    ctx.fill();
    start += angle;
  });
  ctx.globalCompositeOperation = "destination-out";
  ctx.beginPath(); ctx.arc(cx,cy,rInner,0,Math.PI*2); ctx.fill();
  ctx.globalCompositeOperation = "source-over";

  ctx.fillStyle = "#151B16"; ctx.font = "bold 15px " + CHART_FONT; ctx.textAlign = "center";
  ctx.fillText(total, cx, cy+5);
  ctx.textAlign = "left";

  let ly = cy - (segments.length*16)/2 + 8;
  const lx = cx + r + 22;
  segments.forEach(seg => {
    ctx.fillStyle = seg.color;
    ctx.fillRect(lx, ly-8, 9, 9);
    ctx.fillStyle = "#151B16";
    ctx.font = "12px " + CHART_FONT;
    ctx.fillText(`${seg.label} (${seg.value})`, lx+14, ly);
    ly += 18;
  });
}

/**
 * drawBarChart(canvas, items, opts)
 * items: [{label, value, color}]
 * opts.valueSuffix: string appended to the value label above each bar (e.g. "h")
 * opts.horizontal: draw horizontal bars instead of vertical columns
 */
function drawBarChart(canvas, items, opts={}){
  if(!canvas) return;
  const {ctx, w, h} = fitCanvas(canvas);
  ctx.clearRect(0,0,w,h);
  if(!items || !items.length){ emptyState(ctx, w, h, opts.emptyMessage); return; }

  const max = Math.max(...items.map(i => i.value), 0.0001);

  if(opts.horizontal){
    const pad = {top:6, right:44, bottom:6, left: opts.labelWidth || 120};
    const rowH = (h - pad.top - pad.bottom) / items.length;
    items.forEach((item, i) => {
      const y = pad.top + i*rowH + rowH*0.22;
      const barH = rowH*0.56;
      const barW = ((w - pad.left - pad.right) * item.value) / max;
      ctx.fillStyle = "#4B554D"; ctx.font = "11.5px " + CHART_FONT; ctx.textAlign = "left";
      ctx.fillText(item.label, 0, y + barH/2 + 4, pad.left - 12);
      ctx.fillStyle = item.color || "#3E8D5C";
      roundRect(ctx, pad.left, y, Math.max(barW,2), barH, 4);
      ctx.fill();
      ctx.fillStyle = "#151B16"; ctx.font = "bold 11.5px " + CHART_FONT;
      ctx.fillText((opts.valuePrefix||"") + item.value + (opts.valueSuffix||""), pad.left + barW + 8, y + barH/2 + 4);
    });
    return;
  }

  const pad = {top:22, right:10, bottom:32, left:10};
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;
  const gap = plotW / items.length;
  const barW = Math.min(gap*0.5, 46);

  items.forEach((item, i) => {
    const barH = (plotH * item.value) / max;
    const x = pad.left + gap*i + (gap-barW)/2;
    const y = pad.top + plotH - barH;
    ctx.fillStyle = item.color || "#3E8D5C";
    roundRect(ctx, x, y, barW, Math.max(barH,2), 5, true);
    ctx.fill();
    ctx.fillStyle = "#151B16"; ctx.font = "bold 11.5px " + CHART_FONT; ctx.textAlign = "center";
    ctx.fillText((opts.valuePrefix||"") + item.value + (opts.valueSuffix||""), x + barW/2, y - 6);
    ctx.fillStyle = "#4B554D"; ctx.font = "11px " + CHART_FONT;
    ctx.fillText(item.label, x + barW/2, pad.top + plotH + 16);
    ctx.textAlign = "left";
  });
}

function roundRect(ctx, x, y, width, height, radius, topOnly){
  const r = Math.min(radius, width/2, height/2);
  ctx.beginPath();
  if(topOnly){
    ctx.moveTo(x, y+height);
    ctx.lineTo(x, y+r);
    ctx.arcTo(x, y, x+r, y, r);
    ctx.lineTo(x+width-r, y);
    ctx.arcTo(x+width, y, x+width, y+r, r);
    ctx.lineTo(x+width, y+height);
    ctx.closePath();
  } else {
    ctx.moveTo(x+r, y);
    ctx.arcTo(x+width, y, x+width, y+height, r);
    ctx.arcTo(x+width, y+height, x, y+height, r);
    ctx.arcTo(x, y+height, x, y, r);
    ctx.arcTo(x, y, x+width, y, r);
    ctx.closePath();
  }
}

window.AgriCharts = {drawLineChart, drawDonut, drawBarChart};
