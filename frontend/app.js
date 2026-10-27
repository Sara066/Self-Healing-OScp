const API_BASE = ''; // same origin: FastAPI serves this file too

const SCENARIOS = [
  {key:'normal', label:'Normal baseline'},
  {key:'runaway', label:'Runaway CPU'},
  {key:'thrashing', label:'Thrashing'},
  {key:'abnormal_combo', label:'Abnormal combo'},
  {key:'deadlock', label:'Deadlock'},
];

const PID_COLORS = ['#e0985a','#5fb3a3','#8a9bd3','#c98fd6','#d6b25f','#6fbf8a','#e07b9e','#7fa8c9'];
function colorForPid(pid, injectedPid){
  if(!pid) return 'var(--panel-2)';
  if(pid === injectedPid) return '#d3596b';
  return PID_COLORS[pid % PID_COLORS.length];
}

let state = { scenario:'normal', data:null, queueChart:null, memChart:null };

function buildTabs(){
  const wrap = document.getElementById('tabs');
  wrap.innerHTML = '';
  SCENARIOS.forEach(s=>{
    const b = document.createElement('button');
    b.className = 'tab' + (s.key===state.scenario ? ' active':'');
    b.textContent = s.label;
    b.onclick = ()=>{ state.scenario = s.key; buildTabs(); };
    wrap.appendChild(b);
  });
}

async function runScenario(){
  const seed = parseInt(document.getElementById('seedInput').value, 10) || 999;
  const btn = document.getElementById('runBtn');
  const statusEl = document.getElementById('statusMsg');
  const results = document.getElementById('results');

  btn.disabled = true;
  results.hidden = true;
  statusEl.className = 'status';
  statusEl.textContent = `Running "${state.scenario}" on the backend…`;

  try{
    const res = await fetch(`${API_BASE}/api/run/${state.scenario}`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({seed, num_frames:32}),
    });
    if(!res.ok){
      const detail = await res.text();
      throw new Error(`${res.status}: ${detail}`);
    }
    state.data = await res.json();
    statusEl.textContent = '';
    results.hidden = false;
    render();
  } catch(err){
    statusEl.className = 'status error';
    statusEl.textContent = `Run failed — is the backend running? (${err.message})`;
  } finally{
    btn.disabled = false;
  }
}

function renderStats(){
  const d = state.data;
  const hasTicks = d.ticks.length > 0;
  const cards = [];

  if(hasTicks){
    const ticks = d.ticks.length;
    const totalFaults = d.ticks.reduce((a,r)=>a+(r.page_faults_tick||0),0);
    const peakMem = Math.max(...d.ticks.map(r=>r.mem_used_pct||0));
    const avgQueue = d.ticks.reduce((a,r)=>a+(r.queue_total||0),0) / ticks;
    cards.push({label:'Ticks simulated', val: ticks, cls:''});
    cards.push({label:'Peak memory use', val: peakMem.toFixed(1)+'%', cls:'teal'});
    cards.push({label:'Page faults, total', val: totalFaults, cls:'teal'});
    cards.push({label:'Avg queue depth', val: avgQueue.toFixed(1), cls:'amber'});
  }

  const s = d.summary;
  if(s && s.detected_at_tick != null){
    cards.push({label:'Detected at tick', val: s.detected_at_tick, cls:'rose'});
    cards.push({label:'Ticks to recovery', val: s.ticks_to_recovery ?? '—', cls:'amber'});
  } else if(hasTicks){
    cards.push({label:'Anomalies flagged', val:'0', cls:'sage'});
  }

  document.getElementById('stats').innerHTML = cards.map(c=>
    `<div class="stat"><div class="label">${c.label}</div><div class="val ${c.cls}">${c.val}</div></div>`
  ).join('');
}

function renderPianoRoll(){
  const d = state.data;
  const rollPanel = document.getElementById('rollPanel');
  if(d.ticks.length === 0){ rollPanel.style.display = 'none'; return; }
  rollPanel.style.display = '';

  const injectedPid = d.summary ? d.summary.injected_pid : null;
  const canvas = document.getElementById('pianoRoll');
  const wrap = document.getElementById('rollWrap');
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = Math.max(wrap.clientWidth, d.ticks.length * 5);
  const cssHeight = 64;
  canvas.style.width = cssWidth+'px';
  canvas.style.height = cssHeight+'px';
  canvas.width = cssWidth*dpr; canvas.height = cssHeight*dpr;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,cssWidth,cssHeight);

  const n = d.ticks.length;
  const w = cssWidth / n;
  d.ticks.forEach((row,i)=>{
    const pid = row.running_pid;
    ctx.fillStyle = !pid ? 'rgba(255,255,255,.05)' : colorForPid(pid, injectedPid);
    ctx.fillRect(i*w, 18, Math.max(w-0.4,1), cssHeight-24);
  });

  if(d.summary){
    const marks = [
      {t:d.summary.detected_at_tick, color:'#d3596b'},
      {t:d.summary.recovery_applied_tick, color:'#e0985a'},
      {t:d.summary.recovered_confirmed_tick, color:'#84b26a'},
    ];
    marks.forEach(m=>{
      if(m.t==null) return;
      const idx = d.ticks.findIndex(r=>r.tick===m.t);
      if(idx<0) return;
      const x = idx*w + w/2;
      ctx.fillStyle = m.color;
      ctx.beginPath();
      ctx.moveTo(x-4,10); ctx.lineTo(x+4,10); ctx.lineTo(x,17); ctx.closePath();
      ctx.fill();
    });
  }

  canvas.onmousemove = (e)=>{
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const idx = Math.min(n-1, Math.max(0, Math.floor(x / (rect.width/n))));
    const pid = d.ticks[idx].running_pid;
    document.getElementById('rollLabel').textContent =
      `tick ${d.ticks[idx].tick} — ${!pid ? 'CPU idle' : 'PID '+pid+' running'}`;
  };
  canvas.onmouseleave = ()=>{ document.getElementById('rollLabel').innerHTML = '&nbsp;'; };

  const seen = [...new Set(d.ticks.map(r=>r.running_pid).filter(Boolean))].sort((a,b)=>a-b);
  document.getElementById('rollLegend').innerHTML = seen.map(pid=>
    `<span><span class="sw" style="background:${colorForPid(pid, injectedPid)}"></span>PID ${pid}${pid===injectedPid?' (injected)':''}</span>`
  ).join('') + (d.summary && d.summary.detected_at_tick!=null ? '<span><span class="sw" style="background:#d3596b;border-radius:50%"></span>detected</span><span><span class="sw" style="background:#e0985a;border-radius:50%"></span>recovery</span><span><span class="sw" style="background:#84b26a;border-radius:50%"></span>verified</span>' : '');
}

function gridOpt(){ return { color:'#33455533', drawTicks:false }; }
function tickOpt(){ return { color:'#8ba0b2', font:{family:'IBM Plex Mono', size:10} }; }

function renderCharts(){
  const d = state.data;
  const chartsRow = document.getElementById('chartsRow');
  if(d.ticks.length === 0){ chartsRow.style.display = 'none'; return; }
  chartsRow.style.display = '';

  const t = d.ticks.map(r=>r.tick);

  if(state.queueChart) state.queueChart.destroy();
  state.queueChart = new Chart(document.getElementById('queueChart').getContext('2d'), {
    data:{
      labels:t,
      datasets:[
        {type:'line', label:'processes waiting', data:d.ticks.map(r=>r.queue_total), borderColor:'#e0985a', backgroundColor:'#e0985a33', fill:true, tension:.25, pointRadius:0, borderWidth:1.5, yAxisID:'y'},
        {type:'line', label:'avg wait (ticks)', data:d.ticks.map(r=>r.avg_wait), borderColor:'#8a9bd3', pointRadius:0, borderWidth:1.5, tension:.2, yAxisID:'y1'},
      ]
    },
    options:{
      responsive:true, maintainAspectRatio:false, animation:false,
      interaction:{mode:'index', intersect:false},
      plugins:{ legend:{ labels:{ color:'#8ba0b2', font:{family:'IBM Plex Sans', size:11}, boxWidth:10 } } },
      scales:{
        x:{ grid:gridOpt(), ticks:{...tickOpt(), maxTicksLimit:8} },
        y:{ position:'left', beginAtZero:true, grid:gridOpt(), ticks:tickOpt(), title:{display:true,text:'waiting',color:'#8ba0b2',font:{size:11}} },
        y1:{ position:'right', beginAtZero:true, grid:{display:false}, ticks:tickOpt(), title:{display:true,text:'avg wait',color:'#8ba0b2',font:{size:11}} },
      }
    }
  });

  if(state.memChart) state.memChart.destroy();
  state.memChart = new Chart(document.getElementById('memChart').getContext('2d'), {
    data:{
      labels:t,
      datasets:[
        {type:'bar', label:'page faults', data:d.ticks.map(r=>r.page_faults_tick), backgroundColor:'#d3596b99', yAxisID:'y1', barThickness:2},
        {type:'line', label:'memory used %', data:d.ticks.map(r=>r.mem_used_pct), borderColor:'#5fb3a3', pointRadius:0, borderWidth:1.75, tension:.2, yAxisID:'y'},
      ]
    },
    options:{
      responsive:true, maintainAspectRatio:false, animation:false,
      interaction:{mode:'index', intersect:false},
      plugins:{ legend:{ labels:{ color:'#8ba0b2', font:{family:'IBM Plex Sans', size:11}, boxWidth:10 } } },
      scales:{
        x:{ grid:gridOpt(), ticks:{...tickOpt(), maxTicksLimit:8} },
        y:{ position:'left', min:0, max:100, grid:gridOpt(), ticks:tickOpt(), title:{display:true,text:'mem %',color:'#8ba0b2',font:{size:11}} },
        y1:{ position:'right', min:0, grid:{display:false}, ticks:tickOpt(), title:{display:true,text:'faults',color:'#8ba0b2',font:{size:11}} },
      }
    }
  });
}

function renderEvents(){
  const d = state.data;
  const s = d.summary;
  const desc = document.getElementById('eventsDesc');
  const list = document.getElementById('eventsList');

  if(d.scenario === 'deadlock'){
    desc.textContent = 'Graph-based detection over the resource-allocation graph, not tick-driven.';
    list.innerHTML = d.narrative.map(line=>`<li style="grid-template-columns:1fr;"><span class="desc mono">${line}</span></li>`).join('');
    return;
  }

  if(!s || s.detected_at_tick == null){
    desc.textContent = 'Nothing to report — every tick in this run stayed inside the normal operating envelope.';
    list.innerHTML = '<p class="empty-note">No anomalies were flagged during this run.</p>';
    return;
  }

  desc.textContent = `Diagnosis: ${s.diagnosis.replace('_',' ')}, targeting PID ${s.target_pid}.`;
  const rows = [
    {tick:s.detected_at_tick, tag:'detect', text:`anomaly detected on PID ${s.target_pid} — diagnosed as ${s.diagnosis.replace('_',' ')}`},
    {tick:s.recovery_applied_tick, tag:'recover', text: s.action},
    {tick:s.recovered_confirmed_tick, tag:'verify', text: s.recovered_confirmed_tick!=null ? 'metrics confirmed back within the normal range' : 'not yet confirmed within this run'},
  ];
  list.innerHTML = rows.map(r=>
    `<li><span class="tick">tick ${r.tick ?? '—'}</span><span class="tag ${r.tag}">${r.tag}</span><span class="desc">${r.text}</span></li>`
  ).join('');
}

function render(){
  renderStats();
  renderPianoRoll();
  renderCharts();
  renderEvents();
}

document.getElementById('runBtn').addEventListener('click', runScenario);
window.addEventListener('resize', ()=>{ if(state.data) renderPianoRoll(); });

buildTabs();
