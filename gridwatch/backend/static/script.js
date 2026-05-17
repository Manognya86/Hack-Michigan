// GridWatch AI – Full Frontend with working 3D modal close
const API_BASE = '';
let currentPoles = [], currentWeather = null, selectedPole = null, currentTab = 'map';
let leafletMap = null, stormMode = false, stormData = null;
let heatLayer = null;
let threeRenderer = null, threeScene = null, threeCamera = null, threeAnimationId = null;
const RISK_COLORS = { Critical: '#E24B4A', High: '#EF9F27', Medium: '#378ADD', Low: '#639922' };
function getRiskLevel(score) { if (score>=70) return 'Critical'; if (score>=45) return 'High'; if (score>=25) return 'Medium'; return 'Low'; }

async function apiCall(endpoint, method='GET', body=null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`${API_BASE}${endpoint}`, opts);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

async function loadRegion(refresh=false) {
    if (refresh) await apiCall('/api/refresh','POST');
    const data = await apiCall('/api/region');
    currentPoles = data.poles || [];
    currentWeather = data.weather;
    document.getElementById('statsBar').innerHTML = renderStats(data.stats);
    document.getElementById('weatherBadge').innerHTML = renderWeatherBadge(currentWeather);
    renderPoleList();
    if (leafletMap) updateMapMarkers();
    updateSavingsDisplay();
}
function renderStats(stats) {
    if (!stats) return '';
    return `<div class="stat-item"><div class="stat-label">TOTAL POLES</div><div class="stat-value" style="color:#5DCAA5">${stats.total}</div></div>
            <div class="stat-item"><div class="stat-label">CRITICAL</div><div class="stat-value" style="color:#E24B4A">${stats.critical}</div></div>
            <div class="stat-item"><div class="stat-label">HIGH</div><div class="stat-value" style="color:#EF9F27">${stats.high}</div></div>
            <div class="stat-item"><div class="stat-label">MEDIUM</div><div class="stat-value" style="color:#378ADD">${stats.medium}</div></div>
            <div class="stat-item"><div class="stat-label">LOW</div><div class="stat-value" style="color:#639922">${stats.low}</div></div>
            <div class="stat-item"><div class="stat-label">AVG RISK</div><div class="stat-value" style="color:#EF9F27">${stats.avg_risk}/100</div></div>
            <div class="stat-item"><div class="stat-label">PRIORITY BUDGET</div><div class="stat-value" style="color:#E24B4A">$${Math.round(stats.priority_cost_usd/1000)}K</div></div>`;
}
function renderWeatherBadge(weather) {
    if (!weather) return 'Loading...';
    const c = weather.current || {};
    return `💨 ${c.wind_mph||0}mph  💧 ${c.precipitation_in||0}"  ${c.weather_desc||''} (${weather.source})`;
}
function renderPoleList() {
    const filter = document.getElementById('filterRisk').value;
    let filtered = currentPoles.filter(p => { const l = getRiskLevel(p.risk_score).toLowerCase(); return filter==='all' || l===filter; });
    filtered.sort((a,b)=> (b.risk_score||0)-(a.risk_score||0));
    const container = document.getElementById('poleListContainer');
    container.innerHTML = filtered.map(pole => {
        const level = getRiskLevel(pole.risk_score), color = RISK_COLORS[level];
        const isStorm = stormMode && (pole.will_fail || pole.storm_failure_probability>0.65);
        const isSelected = selectedPole && selectedPole.pole_id === pole.pole_id;
        return `<div class="pole-item ${isSelected?'selected':''} ${isStorm?'storm-risk':''}" data-id="${pole.pole_id}">
                    <div class="pole-header"><span class="pole-id">${pole.pole_id}</span><span class="pole-risk-badge" style="background:${color}22; color:${color}">${level.toUpperCase()}</span></div>
                    <div class="pole-district">${pole.district}</div>
                    <div class="pole-risk-bar"><div class="risk-bar-bg"><div class="risk-bar-fill" style="width:${pole.risk_score}%; background:${color}"></div></div>
                    <span class="risk-score" style="color:${color}">${pole.risk_score}</span>${isStorm?'<span style="color:#E24B4A; font-size:9px;">⚡</span>':''}</div>
                </div>`;
    }).join('');
    document.querySelectorAll('.pole-item').forEach(el => el.addEventListener('click', () => { const id = el.dataset.id; const p = currentPoles.find(p => p.pole_id===id); if(p) selectPole(p); }));
}
function selectPole(pole) { selectedPole = pole; renderPoleList(); if(currentTab==='detail') renderDetailView(); if(currentTab==='ai') renderAIView(); if(currentTab==='cv') renderCVView(); updateRightPanel(); }

function initMap() {
    leafletMap = L.map('map').setView([42.33,-83.10],11);
    let dark = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{attribution:'©OpenStreetMap ©CartoDB',subdomains:'abcd'});
    let sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'Tiles © Esri'});
    let current = dark;
    dark.addTo(leafletMap);
    let toggle = L.Control.extend({options:{position:'topright'}, onAdd:function(){ let div=L.DomUtil.create('div','leaflet-bar leaflet-control'); div.innerHTML='<button id="toggleSatBtn" style="background:#0F1923;border:1px solid #1D9E75;color:#5DCAA5;padding:6px 10px;border-radius:4px;cursor:pointer;">🌍 Satellite</button>'; div.onclick=()=>{ if(current===dark){ leafletMap.removeLayer(dark); sat.addTo(leafletMap); current=sat; document.getElementById('toggleSatBtn').innerHTML='🌙 Dark Mode'; } else { leafletMap.removeLayer(sat); dark.addTo(leafletMap); current=dark; document.getElementById('toggleSatBtn').innerHTML='🌍 Satellite'; } }; return div; } });
    leafletMap.addControl(new toggle());
    let heatControl = L.Control.extend({options:{position:'topright'}, onAdd:function(){ let div=L.DomUtil.create('div','leaflet-bar leaflet-control'); div.innerHTML='<button id="toggleHeatmapBtn" style="background:#0F1923;border:1px solid #1D9E75;color:#5DCAA5;padding:6px 10px;border-radius:4px;cursor:pointer;margin-top:5px;">🔥 Heatmap</button>'; div.onclick=toggleHeatmap; return div; } });
    leafletMap.addControl(new heatControl());
    updateMapMarkers();
}
async function toggleHeatmap() {
    if (heatLayer) { leafletMap.removeLayer(heatLayer); heatLayer = null; document.getElementById('toggleHeatmapBtn').style.background = '#0F1923'; return; }
    document.getElementById('toggleHeatmapBtn').style.background = '#1D9E75';
    const res = await fetch('/api/heatmap');
    const data = await res.json();
    if (data.points) {
        const points = data.points.map(p => [p.lat, p.lng, p.risk]);
        heatLayer = L.heatLayer(points, { radius: 25, blur: 15, maxZoom: 12 });
        heatLayer.addTo(leafletMap);
    }
}
function updateMapMarkers() {
    if(!leafletMap) return;
    leafletMap.eachLayer(layer=>{ if(layer instanceof L.Marker) leafletMap.removeLayer(layer); });
    currentPoles.forEach(pole=>{
        const level = getRiskLevel(pole.risk_score), color = RISK_COLORS[level];
        const isStorm = stormMode && (pole.will_fail || pole.storm_failure_probability>0.65);
        const isSelected = selectedPole && selectedPole.pole_id===pole.pole_id;
        const size = isSelected?28:20;
        const html = `<svg width="${size}" height="${size}" viewBox="0 0 20 20">${isStorm?`<circle cx="10" cy="10" r="9" fill="${color}" opacity="0.3"/>`:''}<circle cx="10" cy="10" r="${isSelected?8:6}" fill="${color}" stroke="${isSelected?'#fff':'#000'}" stroke-width="${isSelected?2.5:1}"/>${pole.risk_score>=70?`<text x="10" y="14" text-anchor="middle" fill="white" font-size="9" font-weight="bold">!</text>`:''}</svg>`;
        const icon = L.divIcon({html, iconSize:[size,size], className:isStorm?'storm-marker':''});
        const marker = L.marker([pole.lat,pole.lng],{icon}).addTo(leafletMap);
        marker.bindTooltip(`${pole.pole_id}<br>Risk: ${pole.risk_score}`);
        marker.on('click',()=>selectPole(pole));
    });
}

function switchTab(tabId) {
    currentTab = tabId;
    document.querySelectorAll('.tab-btn').forEach(btn=>btn.classList.remove('active'));
    document.querySelector(`.tab-btn[data-tab="${tabId}"]`).classList.add('active');
    document.querySelectorAll('.tab-pane').forEach(pane=>pane.classList.remove('active'));
    document.getElementById(`${tabId}View`).classList.add('active');
    if(tabId==='map' && leafletMap) leafletMap.invalidateSize();
    if(tabId==='detail') renderDetailView();
    if(tabId==='cv') renderCVView();
    if(tabId==='ai') renderAIView();
    if(tabId==='storm') renderStormView();
    if(tabId==='analytics') renderAnalytics();
    if(tabId==='predict') renderCustomPredict();
    if(tabId==='priority') renderPriorityView();
}

function renderDetailView() {
    const container = document.getElementById('detailView');
    if(!selectedPole) { container.innerHTML='<div class="card">Select a pole</div>'; return; }
    const p = selectedPole, level = getRiskLevel(p.risk_score), color = RISK_COLORS[level];
    const opt = p.optimal_action || {};
    const env = p.environmental_factors || { aqi: p.aqi || 'N/A', soil_moisture: p.soil_moisture || 'N/A' };
    container.innerHTML = `<div class="card"><div style="display:flex;justify-content:space-between"><div><h3>${p.pole_id}</h3><div>${p.district}</div></div><div><span style="font-size:36px;font-weight:bold;color:${color}">${p.risk_score}</span><br>RISK SCORE</div></div>
        <div class="risk-bar-bg" style="margin:10px 0;"><div class="risk-bar-fill" style="width:${p.risk_score}%;background:${color}"></div></div>
        <div><strong>Material:</strong> ${p.material} | <strong>Age:</strong> ${p.age} yrs | <strong>Tilt:</strong> ${p.tilt_angle}°</div>
        <div><strong>Cracks:</strong> ${p.crack_detected?'Yes':'No'} | <strong>Rust:</strong> ${p.rust_detected?'Yes':'No'}</div>
        <div><strong>Vegetation:</strong> ${p.vegetation_risk} | <strong>Wind:</strong> ${p.wind_exposure}</div>
        <div><strong>Flood Zone:</strong> ${p.flood_zone} | <strong>Soil:</strong> ${p.soil_type}</div>
        <div><strong>AQI:</strong> ${env.aqi} | <strong>Soil Moisture:</strong> ${env.soil_moisture}</div>
        <hr><div><strong>Failure Prob:</strong> ${(p.failure_probability*100).toFixed(0)}%</div>
        <div><strong>Storm Failure:</strong> ${(p.storm_failure_probability*100).toFixed(0)}%</div>
        <div><strong>Remaining Life:</strong> ${p.remaining_life_years} yrs</div>
        <div><strong>Replace Cost:</strong> $${p.replace_cost_usd.toLocaleString()}</div>
        <div><strong>Repair Cost:</strong> $${p.repair_cost_usd.toLocaleString()}</div>
        <div><strong>Priority Score:</strong> <span style="color:${p.priority_score>=70?'#E24B4A':p.priority_score>=45?'#EF9F27':'#5DCAA5'}">${p.priority_score}</span></div>
        <div><strong>Optimal Action:</strong> ${opt.action || p.recommendation?.replace(/_/g,' ')}<br><span style="font-size:10px; color:#4a6070;">${opt.rationale || ''}</span></div>
        <div style="display:flex; gap:10px; margin-top:12px; flex-wrap:wrap;">
            <button id="explainBtn" class="btn-secondary">🔍 Explain Diagnosis</button>
            <button id="view3DBtn" class="btn-secondary">3D View</button>
            <button id="feedbackFailedBtn" class="btn-secondary" style="background:#2A0F0F;">⚠️ Mark Failed</button>
            <button id="feedbackRepairedBtn" class="btn-secondary">🔧 Repaired</button>
            <button id="feedbackReplacedBtn" class="btn-secondary">🔄 Replaced</button>
        </div>
        <div id="explanationText" style="margin-top:10px; font-size:11px; background:#0A1520; padding:8px; border-radius:4px; display:none;"></div>
    </div>`;
    document.getElementById('explainBtn')?.addEventListener('click', async () => {
        const div = document.getElementById('explanationText');
        div.style.display = 'block';
        div.innerHTML = 'Loading...';
        try {
            const res = await fetch(`${API_BASE}/api/explain/${p.pole_id}`);
            const data = await res.json();
            div.innerHTML = `<strong>📋 Diagnosis</strong><br>${data.summary}<br><br><strong>⚡ Severity</strong><br>${data.severity}<br><br><strong>⏳ Time to Failure</strong><br>Estimated ${data.remaining_life_months} months (range ${data.confidence_interval_months})<br><br><strong>🔧 Top Factors</strong><br>${data.top_contributing_factors.map(f => `• ${f.factor}: ${f.contribution} pts`).join('<br>')}`;
        } catch(e) { div.innerHTML = `Error: ${e.message}`; }
    });
    document.getElementById('view3DBtn')?.addEventListener('click', () => open3DView(p));
    document.getElementById('feedbackFailedBtn')?.addEventListener('click', async () => {
        await fetch(`${API_BASE}/api/feedback/${p.pole_id}?feedback=failed`, { method: 'POST' });
        alert('Feedback recorded: Failed');
    });
    document.getElementById('feedbackRepairedBtn')?.addEventListener('click', async () => {
        await fetch(`${API_BASE}/api/feedback/${p.pole_id}?feedback=repaired`, { method: 'POST' });
        await fetch(`${API_BASE}/api/record_action/${p.pole_id}?action=repaired`, { method: 'POST' });
        alert('Action recorded: Repaired');
        updateSavingsDisplay();
    });
    document.getElementById('feedbackReplacedBtn')?.addEventListener('click', async () => {
        await fetch(`${API_BASE}/api/feedback/${p.pole_id}?feedback=replaced`, { method: 'POST' });
        await fetch(`${API_BASE}/api/record_action/${p.pole_id}?action=replaced`, { method: 'POST' });
        alert('Action recorded: Replaced');
        updateSavingsDisplay();
    });
}

// 3D View with proper close and cleanup
async function open3DView(pole) {
    const modal = document.getElementById('threeDModal');
    modal.style.display = 'block';
    const canvas = document.getElementById('threeCanvas');
    // Clean up previous scene if any
    if (threeRenderer) {
        if (threeAnimationId) cancelAnimationFrame(threeAnimationId);
        threeRenderer.dispose();
        threeScene = null; threeCamera = null; threeRenderer = null;
    }
    const res = await fetch(`${API_BASE}/api/3d_model/${pole.pole_id}`);
    const data = await res.json();
    const width = canvas.clientWidth, height = canvas.clientHeight;
    threeScene = new THREE.Scene();
    threeCamera = new THREE.PerspectiveCamera(45, width/height, 0.1, 1000);
    threeRenderer = new THREE.WebGLRenderer({ canvas });
    threeRenderer.setSize(width, height);
    const geometry = new THREE.CylinderGeometry(0.5, 0.5, data.height/10, 32);
    const material = new THREE.MeshStandardMaterial({ color: data.color });
    const cylinder = new THREE.Mesh(geometry, material);
    threeScene.add(cylinder);
    const light = new THREE.AmbientLight(0x404040);
    threeScene.add(light);
    threeCamera.position.z = 5;
    function animate() {
        threeAnimationId = requestAnimationFrame(animate);
        if (threeRenderer && threeScene && threeCamera) {
            threeRenderer.render(threeScene, threeCamera);
        }
    }
    animate();
    document.getElementById('damageText').innerText = `Crack:${data.damage.crack?'Yes':'No'} Rust:${data.damage.rust?'Yes':'No'} Tilt:${data.damage.tilt}°`;
}

// Ensure close button works and cleanup 3D resources
function setupModalClose() {
    const modal = document.getElementById('threeDModal');
    const closeBtn = document.getElementById('close3DBtn');
    if (closeBtn) {
        closeBtn.onclick = () => {
            modal.style.display = 'none';
            if (threeRenderer) {
                if (threeAnimationId) cancelAnimationFrame(threeAnimationId);
                threeRenderer.dispose();
                threeScene = null; threeCamera = null; threeRenderer = null;
            }
        };
    }
    // Also close when clicking outside the modal content
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
            if (threeRenderer) {
                if (threeAnimationId) cancelAnimationFrame(threeAnimationId);
                threeRenderer.dispose();
                threeScene = null; threeCamera = null; threeRenderer = null;
            }
        }
    });
}

async function updateSavingsDisplay() {
    try {
        const savings = await apiCall('/api/savings');
        const elem = document.getElementById('savingsDisplay');
        if (elem) elem.innerHTML = `<div class="stat-item"><div class="stat-label">💰 TOTAL SAVINGS (PROACTIVE vs OUTAGE)</div><div class="stat-value" style="color:#5DCAA5">$${Math.round(savings.total_savings).toLocaleString()}</div></div>`;
    } catch(e) { console.error('Savings error', e); }
}

function renderCVView() {
    const container = document.getElementById('cvView');
    container.innerHTML = `<div class="card"><div class="card-title">COMPUTER VISION INSPECTION</div><input type="file" id="cvImage" accept="image/*"><button id="analyzeCvBtn" class="btn-secondary" style="margin-top:10px;">Analyze Image</button><div id="cvResult" style="margin-top:15px;"></div></div>`;
    document.getElementById('analyzeCvBtn')?.addEventListener('click', async()=>{
        const file = document.getElementById('cvImage').files[0];
        if(!file) return;
        const fd = new FormData(); fd.append('file',file);
        if(selectedPole) fd.append('pole_id',selectedPole.pole_id);
        const res = await fetch(`${API_BASE}/api/cv/analyze`,{method:'POST',body:fd});
        const data = await res.json();
        document.getElementById('cvResult').innerHTML = `<pre>${JSON.stringify(data,null,2)}</pre>`;
        if(data.updated_prediction) { Object.assign(selectedPole, data.updated_prediction); renderDetailView(); }
    });
}

async function renderAIView() {
    const container = document.getElementById('aiView');
    if(!selectedPole) { container.innerHTML='<div class="card">Select a pole</div>'; return; }
    container.innerHTML = `<div class="card"><div class="card-title">AI Recommendations</div><button id="aiMaintenanceBtn" class="btn-secondary">Maintenance Recommendation</button><button id="aiWorkOrderBtn" class="btn-secondary">Work Order</button><button id="aiScheduleBtn" class="btn-secondary">5-Year Schedule</button><div id="aiResponse" style="margin-top:15px;white-space:pre-wrap;"></div></div>`;
    document.getElementById('aiMaintenanceBtn').onclick = ()=>callAI('maintenance');
    document.getElementById('aiWorkOrderBtn').onclick = ()=>callAI('work_order');
    document.getElementById('aiScheduleBtn').onclick = ()=>callAI('schedule');
}
async function callAI(type) {
    const resp = document.getElementById('aiResponse');
    resp.innerHTML = '⏳ Generating...';
    try {
        const data = await apiCall('/api/ai/recommend','POST',{pole_id:selectedPole.pole_id, prompt_type:type});
        resp.innerHTML = data.ai_response;
    } catch(e) { resp.innerHTML = 'Error: '+e.message; }
}

function renderStormView() {
    const container = document.getElementById('stormView');
    container.innerHTML = `<div class="card"><div class="card-title">STORM SIMULATION</div><label>Wind (mph): <input type="range" id="stormWind" min="10" max="100" value="60"> <span id="windVal">60</span></label><br>
        <label>Gusts (mph): <input type="range" id="stormGust" min="15" max="130" value="78"> <span id="gustVal">78</span></label><br>
        <label>Precip (in): <input type="range" id="stormPrecip" min="0" max="6" step="0.1" value="2"> <span id="precipVal">2.0</span></label><br>
        <button id="runStormSim" class="btn-secondary">Run Simulation</button><div id="stormResults"></div></div>`;
    document.getElementById('stormWind').oninput = e=>document.getElementById('windVal').innerText=e.target.value;
    document.getElementById('stormGust').oninput = e=>document.getElementById('gustVal').innerText=e.target.value;
    document.getElementById('stormPrecip').oninput = e=>document.getElementById('precipVal').innerText=e.target.value;
    document.getElementById('runStormSim').onclick = async ()=>{
        const wind = parseFloat(document.getElementById('stormWind').value);
        const gust = parseFloat(document.getElementById('stormGust').value);
        const precip = parseFloat(document.getElementById('stormPrecip').value);
        const res = await apiCall('/api/storm/simulate','POST',{wind_mph:wind, gust_mph:gust, precipitation_in:precip});
        stormMode = true; stormData = res;
        document.getElementById('stormResults').innerHTML = `<pre>${JSON.stringify(res.impact,null,2)}</pre>`;
        renderPoleList(); updateMapMarkers();
        const banner = document.getElementById('stormBanner');
        banner.style.display = 'flex';
        banner.innerHTML = `⚡ STORM SIMULATION ACTIVE — ${res.impact.poles_failing} poles failing · ${res.impact.estimated_customers_affected?.toLocaleString()} customers affected <button id="clearStormBtn" class="btn-secondary" style="margin-left:auto;">Clear</button>`;
        document.getElementById('clearStormBtn').onclick = ()=>{ stormMode=false; stormData=null; loadRegion(); banner.style.display='none'; };
    };
}

async function renderAnalytics() {
    const container = document.getElementById('analyticsView');
    container.innerHTML = '<div class="card">Loading analytics...</div>';
    const data = await apiCall('/api/analytics');
    container.innerHTML = `<div class="card"><canvas id="riskHistogram" width="400" height="200"></canvas></div><div class="card"><canvas id="featureImportance" width="400" height="200"></canvas></div><div class="card"><pre>${JSON.stringify(data.model_metrics,null,2)}</pre></div>`;
    if(data.risk_histogram) new Chart(document.getElementById('riskHistogram'),{type:'bar',data:{labels:data.risk_histogram.map(d=>d.range),datasets:[{label:'Poles',data:data.risk_histogram.map(d=>d.count),backgroundColor:'#378ADD'}]}});
    if(data.feature_importance) new Chart(document.getElementById('featureImportance'),{type:'bar',data:{labels:data.feature_importance.slice(0,8).map(f=>f.feature),datasets:[{label:'Importance',data:data.feature_importance.slice(0,8).map(f=>f.importance),backgroundColor:'#5DCAA5'}]}});
}

function renderCustomPredict() {
    const container = document.getElementById('predictView');
    container.innerHTML = `<div class="card"><div class="card-title">CUSTOM POLE PREDICTION</div><label>Age: <input type="number" id="predAge" value="25"></label><br>
        <label>Tilt: <input type="number" id="predTilt" value="5" step="0.5"></label><br>
        <label>Material: <select id="predMaterial"><option>Wood</option><option>Steel</option><option>Concrete</option></select></label><br>
        <label>Crack: <input type="checkbox" id="predCrack"></label><br>
        <label>Rust: <input type="checkbox" id="predRust"></label><br>
        <label>Vegetation: <select id="predVeg"><option>low</option><option>medium</option><option>high</option></select></label><br>
        <label>Flood Zone: <select id="predFlood"><option>X</option><option>AE</option><option>A</option></select></label><br>
        <button id="runCustomPredict" class="btn-secondary">Predict</button><div id="customResult"></div></div>`;
    document.getElementById('runCustomPredict').onclick = async ()=>{
        const body = { age:parseInt(document.getElementById('predAge').value), tilt_angle:parseFloat(document.getElementById('predTilt').value), material:document.getElementById('predMaterial').value, crack_detected:document.getElementById('predCrack').checked, rust_detected:document.getElementById('predRust').checked, vegetation_risk:document.getElementById('predVeg').value, flood_zone:document.getElementById('predFlood').value };
        const res = await apiCall('/api/predict','POST',body);
        document.getElementById('customResult').innerHTML = `<pre>${JSON.stringify(res,null,2)}</pre>`;
    };
}

async function renderPriorityView() {
    const container = document.getElementById('priorityView');
    container.innerHTML = '<div class="card">Loading priority list...</div>';
    try {
        const data = await apiCall('/api/priority');
        if (data.error) { container.innerHTML = `<div class="card">${data.error}</div>`; return; }
        const poles = data.top_priority_poles || [];
        container.innerHTML = `<div class="card"><div class="card-title">TOP 20 URGENT POLES (by Priority Score)</div>
            <table style="width:100%; font-size:11px; border-collapse:collapse;">
                <thead><tr style="border-bottom:1px solid #1a2e3b; text-align:left;"><th>Rank</th><th>Pole ID</th><th>District</th><th>Priority</th><th>Risk</th><th>Storm Fail %</th><th>Recommendation</th></td></thead>
                <tbody>${poles.map((p, idx) => `<tr style="border-bottom:1px solid #1a2e3b;">
                    <td style="padding:6px 4px;">${idx+1}</td>
                    <td style="padding:6px 4px;"><strong>${p.pole_id}</strong></td>
                    <td style="padding:6px 4px;">${p.district}</td>
                    <td style="padding:6px 4px;">${p.priority_score}</td>
                    <td style="padding:6px 4px;">${p.risk_score}</td>
                    <td style="padding:6px 4px;">${(p.storm_failure_probability*100).toFixed(0)}%</td>
                    <td style="padding:6px 4px;">${p.recommendation?.replace(/_/g,' ')}</td>
                </tr>`).join('')}</tbody>
            </table><div style="margin-top:12px; font-size:9px; color:#4a6070;">Priority = 0.5*Risk + 0.3*StormProb + 0.2*CostNorm</div></div>`;
    } catch(e) { container.innerHTML = `<div class="card">Error: ${e.message}</div>`; }
}

function updateRightPanel() {
    const panel = document.getElementById('rightPanel');
    if(!selectedPole) { panel.innerHTML = '<div class="card">Select a pole</div>'; return; }
    const p = selectedPole, level = getRiskLevel(p.risk_score), color = RISK_COLORS[level];
    panel.innerHTML = `<div class="card"><div class="card-title">SELECTED</div><div style="font-size:18px;font-weight:600;">${p.pole_id}</div><div>${p.district}</div><div style="font-size:36px;color:${color};">${p.risk_score}</div><div>RISK SCORE</div><div>Priority: ${p.priority_score}</div><button id="quickAI" class="btn-secondary" style="margin-top:10px;">AI Recommendation</button></div>`;
    document.getElementById('quickAI')?.addEventListener('click',()=>{ switchTab('ai'); callAI('maintenance'); });
}

document.addEventListener('DOMContentLoaded', async()=>{
    await loadRegion();
    initMap();
    setupModalClose();  // attach close event to 3D modal
    document.querySelectorAll('.tab-btn').forEach(btn=>btn.addEventListener('click',()=>switchTab(btn.dataset.tab)));
    document.getElementById('refreshBtn').addEventListener('click',()=>loadRegion(true));
    document.getElementById('filterRisk').addEventListener('change',()=>renderPoleList());
    switchTab('map');
});
// Add storm marker style
if (!document.querySelector('#stormAnimationStyle')) {
    const style = document.createElement('style');
    style.id = 'stormAnimationStyle';
    style.textContent = `.storm-marker { animation: storm-pulse 1.5s ease-in-out infinite; } @keyframes storm-pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.7; transform: scale(1.3); } }`;
    document.head.appendChild(style);
}