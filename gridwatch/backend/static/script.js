// GridWatch AI – Full Frontend with CSV, History, Budget Simulator
const API_BASE = '';
let currentPoles = [], currentWeather = null, selectedPole = null, currentTab = 'map';
let leafletMap = null, stormMode = false, stormData = null;
let heatLayer = null;
let threeRenderer = null, threeScene = null, threeCamera = null, threeAnimationId = null;
let historyChart = null;
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
function selectPole(pole) { selectedPole = pole; renderPoleList(); if(currentTab==='detail') renderDetailView(); if(currentTab==='ai') renderAIView(); if(currentTab==='cv') renderCVView(); if(currentTab==='history') renderHistoryView(); updateRightPanel(); }

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
    if(tabId==='history') renderHistoryView();
    if(tabId==='budget') renderBudgetSimulator();
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

async function open3DView(pole) {
    const modal = document.getElementById('threeDModal');
    modal.style.display = 'block';
    const canvas = document.getElementById('threeCanvas');
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
        if (threeRenderer && threeScene && threeCamera) threeRenderer.render(threeScene, threeCamera);
    }
    animate();
    document.getElementById('damageText').innerText = `Crack:${data.damage.crack?'Yes':'No'} Rust:${data.damage.rust?'Yes':'No'} Tilt:${data.damage.tilt}°`;
}

function setupModalClose() {
    const modal = document.getElementById('threeDModal');
    const closeBtn = document.getElementById('close3DBtn');
    const closeHandler = () => {
        modal.style.display = 'none';
        if (threeRenderer) {
            if (threeAnimationId) cancelAnimationFrame(threeAnimationId);
            threeRenderer.dispose();
            threeScene = null; threeCamera = null; threeRenderer = null;
        }
    };
    if (closeBtn) closeBtn.onclick = closeHandler;
    modal.addEventListener('click', (e) => { if (e.target === modal) closeHandler(); });
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
    container.innerHTML = `<div class="card"><div class="card-title">STORM SIMULATION</div>
        <label>Wind (mph): <input type="range" id="stormWind" min="10" max="100" value="60"> <span id="windVal">60</span></label><br>
        <label>Gusts (mph): <input type="range" id="stormGust" min="15" max="130" value="78"> <span id="gustVal">78</span></label><br>
        <label>Precip (in): <input type="range" id="stormPrecip" min="0" max="6" step="0.1" value="2"> <span id="precipVal">2.0</span></label><br>
        <button id="runStormSim" class="btn-secondary">Run Simulation</button>
        <div id="stormResults"></div>
    </div>`;
    const windSlider = document.getElementById('stormWind');
    const gustSlider = document.getElementById('stormGust');
    const precipSlider = document.getElementById('stormPrecip');
    const windVal = document.getElementById('windVal');
    const gustVal = document.getElementById('gustVal');
    const precipVal = document.getElementById('precipVal');
    if (windSlider) windSlider.oninput = () => windVal.innerText = windSlider.value;
    if (gustSlider) gustSlider.oninput = () => gustVal.innerText = gustSlider.value;
    if (precipSlider) precipSlider.oninput = () => precipVal.innerText = parseFloat(precipSlider.value).toFixed(1);
    const runBtn = document.getElementById('runStormSim');
    if (runBtn) {
        runBtn.onclick = async () => {
            const wind = parseFloat(windSlider.value);
            const gust = parseFloat(gustSlider.value);
            const precip = parseFloat(precipSlider.value);
            const resultsDiv = document.getElementById('stormResults');
            resultsDiv.innerHTML = '⏳ Simulating...';
            try {
                const res = await apiCall('/api/storm/simulate', 'POST', {
                    wind_mph: wind,
                    gust_mph: gust,
                    precipitation_in: precip
                });
                stormMode = true;
                stormData = res;
                resultsDiv.innerHTML = `<pre>${JSON.stringify(res.impact, null, 2)}</pre>`;
                renderPoleList();
                updateMapMarkers();
                const banner = document.getElementById('stormBanner');
                banner.style.display = 'flex';
                banner.innerHTML = `⚡ STORM SIMULATION ACTIVE — ${res.impact.poles_failing} poles failing · ${res.impact.estimated_customers_affected?.toLocaleString()} customers affected <button id="clearStormBtn" class="btn-secondary" style="margin-left:auto;">Clear</button>`;
                document.getElementById('clearStormBtn').onclick = () => {
                    stormMode = false;
                    stormData = null;
                    loadRegion();
                    banner.style.display = 'none';
                };
            } catch (e) {
                resultsDiv.innerHTML = `Error: ${e.message}`;
            }
        };
    }
}

async function renderAnalytics() {
    const container = document.getElementById('analyticsView');
    container.innerHTML = '<div class="card">Loading analytics...</div>';
    try {
        const data = await apiCall('/api/analytics');
        container.innerHTML = `
            <div class="card"><h4>Risk Score Distribution</h4><canvas id="riskHistogram" width="400" height="200"></canvas></div>
            <div class="card"><h4>Feature Importance (Top 8)</h4><canvas id="featureImportance" width="400" height="200"></canvas></div>
            <div class="card"><h4>Average Risk by District</h4><canvas id="districtChart" width="400" height="200"></canvas></div>
            <div class="card"><h4>Model Metrics</h4><pre>${JSON.stringify(data.model_metrics, null, 2)}</pre></div>
        `;
        if (data.risk_histogram && data.risk_histogram.length) {
            new Chart(document.getElementById('riskHistogram'), {
                type: 'bar',
                data: { labels: data.risk_histogram.map(d => d.range), datasets: [{ label: 'Number of Poles', data: data.risk_histogram.map(d => d.count), backgroundColor: '#378ADD' }] },
                options: { responsive: true }
            });
        }
        if (data.feature_importance && data.feature_importance.length) {
            const top = data.feature_importance.slice(0, 8);
            new Chart(document.getElementById('featureImportance'), {
                type: 'bar',
                data: { labels: top.map(f => f.feature), datasets: [{ label: 'Importance', data: top.map(f => f.importance), backgroundColor: '#5DCAA5' }] },
                options: { responsive: true }
            });
        }
        if (data.district_data && data.district_data.length) {
            const districts = data.district_data.slice(0, 10);
            new Chart(document.getElementById('districtChart'), {
                type: 'bar',
                data: { labels: districts.map(d => d.district), datasets: [{ label: 'Average Risk Score', data: districts.map(d => d.avg_risk), backgroundColor: '#EF9F27' }] },
                options: { responsive: true }
            });
        }
    } catch (e) {
        container.innerHTML = `<div class="card">Error loading analytics: ${e.message}</div>`;
    }
}

function renderCustomPredict() {
    const container = document.getElementById('predictView');
    container.innerHTML = `
        <div class="card">
            <div class="card-title">CUSTOM POLE PREDICTION</div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                <div><label title="Age of the pole in years">Age (years):</label><br><input type="number" id="predAge" value="25" style="width:100%"></div>
                <div><label title="Material type">Material:</label><br><select id="predMaterial" style="width:100%"><option>Wood</option><option>Steel</option><option>Concrete</option><option>Composite</option></select></div>
                <div><label title="Tilt angle in degrees, higher = unstable">Tilt Angle (°):</label><br><input type="number" id="predTilt" value="5" step="0.5" style="width:100%"></div>
                <div><label title="Visible cracks on the pole">Cracks detected:</label><br><input type="checkbox" id="predCrack"></div>
                <div><label title="Visible rust or corrosion">Rust detected:</label><br><input type="checkbox" id="predRust"></div>
                <div><label title="Risk from nearby vegetation (high/medium/low)">Vegetation Risk:</label><br><select id="predVeg" style="width:100%"><option>low</option><option>medium</option><option>high</option></select></div>
                <div><label title="Exposure to strong winds">Wind Exposure:</label><br><select id="predWind" style="width:100%"><option>low</option><option>medium</option><option>high</option></select></div>
                <div><label title="FEMA flood zone (AE/A = high flood risk)">Flood Zone:</label><br><select id="predFlood" style="width:100%"><option>X</option><option>AE</option><option>A</option><option>B</option></select></div>
                <div><label title="Pole height in feet; taller poles face higher wind loads">Height (ft):</label><br><input type="number" id="predHeight" value="35" step="1" style="width:100%"></div>
                <div><label title="Distance from road in feet; closer = higher collision risk">Road Proximity (ft):</label><br><input type="number" id="predRoad" value="50" step="5" style="width:100%"></div>
                <div><label title="Number of transformers mounted; extra weight increases risk">Transformers:</label><br><input type="number" id="predXfmr" value="1" min="0" max="3" style="width:100%"></div>
                <div><label title="Year of last maintenance; newer is better">Last Maintenance Year:</label><br><input type="number" id="predMaint" value="2018" min="2010" max="2024" style="width:100%"></div>
                <div><label title="Air Quality Index (0-500); higher = more corrosive">AQI (Air Quality):</label><br><input type="number" id="predAqi" value="50" min="0" max="500" style="width:100%"></div>
                <div><label title="Soil moisture (0-1); wetter soil increases tilt risk">Soil Moisture:</label><br><input type="number" id="predSoil" value="0.5" step="0.1" min="0" max="1" style="width:100%"></div>
            </div>
            <button id="runCustomPredict" class="btn-secondary" style="margin-top:15px;">Run Prediction</button>
            <div id="customResult" style="margin-top:15px;"></div>
        </div>
    `;
    document.getElementById('runCustomPredict').onclick = async () => {
        const body = {
            age: parseInt(document.getElementById('predAge').value),
            material: document.getElementById('predMaterial').value,
            tilt_angle: parseFloat(document.getElementById('predTilt').value),
            crack_detected: document.getElementById('predCrack').checked,
            rust_detected: document.getElementById('predRust').checked,
            vegetation_risk: document.getElementById('predVeg').value,
            wind_exposure: document.getElementById('predWind').value,
            flood_zone: document.getElementById('predFlood').value,
            height_ft: parseFloat(document.getElementById('predHeight').value),
            road_proximity_ft: parseFloat(document.getElementById('predRoad').value),
            num_transformers: parseInt(document.getElementById('predXfmr').value),
            last_maintenance_year: parseInt(document.getElementById('predMaint').value),
            aqi: parseInt(document.getElementById('predAqi').value),
            soil_moisture: parseFloat(document.getElementById('predSoil').value)
        };
        try {
            const res = await apiCall('/api/predict', 'POST', body);
            document.getElementById('customResult').innerHTML = `<pre>${JSON.stringify(res, null, 2)}</pre>`;
        } catch (e) {
            document.getElementById('customResult').innerHTML = `<div class="text-critical">Error: ${e.message}</div>`;
        }
    };
}

async function renderPriorityView() {
    const container = document.getElementById('priorityView');
    container.innerHTML = '<div class="card">Loading priority list...</div>';
    try {
        const data = await apiCall('/api/priority');
        if (data.error) { container.innerHTML = `<div class="card">${data.error}</div>`; return; }
        const poles = data.top_priority_poles || [];
        container.innerHTML = `
            <div class="card">
                <div class="card-title">TOP 20 URGENT POLES (by Priority Score)</div>
                <div style="overflow-x:auto;">
                    <table style="width:100%; font-size:11px; border-collapse:collapse;">
                        <thead><tr style="border-bottom:1px solid #1a2e3b; text-align:left;">
                            <th>Rank</th><th>Pole ID</th><th>District</th><th>Priority</th><th>Risk</th><th>Storm Fail %</th><th>Recommendation</th>
                        </td></thead>
                        <tbody id="priorityTableBody">
                            ${poles.map((p, idx) => `
                                <tr class="priority-row" data-pole-id="${p.pole_id}" style="border-bottom:1px solid #1a2e3b; cursor:pointer; transition:background 0.1s;">
                                    <td style="padding:6px 4px;">${idx+1}</td>
                                    <td style="padding:6px 4px;"><strong>${p.pole_id}</strong></td>
                                    <td style="padding:6px 4px;">${p.district}</td>
                                    <td style="padding:6px 4px;">${p.priority_score}</td>
                                    <td style="padding:6px 4px;">${p.risk_score}</td>
                                    <td style="padding:6px 4px;">${(p.storm_failure_probability*100).toFixed(0)}%</td>
                                    <td style="padding:6px 4px;">${p.recommendation?.replace(/_/g,' ')}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                <div style="margin-top:12px; font-size:9px; color:#4a6070;">Priority = 0.5*Risk + 0.3*StormProb + 0.2*CostNorm<br>✨ Click on any row to locate the pole on the map.</div>
            </div>
        `;
        document.querySelectorAll('.priority-row').forEach(row => {
            row.addEventListener('mouseenter', () => row.style.background = '#0F2A1F');
            row.addEventListener('mouseleave', () => row.style.background = '');
            row.addEventListener('click', () => {
                const poleId = row.dataset.poleId;
                const pole = currentPoles.find(p => p.pole_id === poleId);
                if (pole) {
                    selectPole(pole);
                    switchTab('map');
                    if (leafletMap) leafletMap.setView([pole.lat, pole.lng], 15);
                } else {
                    alert('Pole not found in current data. Try refreshing the page.');
                }
            });
        });
    } catch(e) {
        container.innerHTML = `<div class="card">Error: ${e.message}</div>`;
    }
}

// ── Risk History Tab ──────────────────────────────────────────────
async function renderHistoryView() {
    const container = document.getElementById('historyView');
    if (!selectedPole) {
        container.innerHTML = '<div class="card">Select a pole to view its risk history.</div>';
        return;
    }
    container.innerHTML = '<div class="card">Loading risk history...</div>';
    try {
        const res = await fetch(`${API_BASE}/api/risk_history/${selectedPole.pole_id}`);
        const data = await res.json();
        if (!data.history || data.history.length === 0) {
            container.innerHTML = `<div class="card">No historical data for ${selectedPole.pole_id}. Data will appear after a few days.</div>`;
            return;
        }
        container.innerHTML = `<div class="card"><h4>Risk Score History for ${selectedPole.pole_id}</h4><canvas id="historyChart" width="400" height="200"></canvas></div>`;
        const ctx = document.getElementById('historyChart').getContext('2d');
        if (historyChart) historyChart.destroy();
        historyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.history.map(h => h.date),
                datasets: [{ label: 'Risk Score', data: data.history.map(h => h.risk), borderColor: '#5DCAA5', fill: false, tension: 0.1 }]
            },
            options: { responsive: true, scales: { y: { min: 0, max: 100 } } }
        });
    } catch(e) {
        container.innerHTML = `<div class="card">Error loading history: ${e.message}</div>`;
    }
}

// ── Budget Simulator Tab ──────────────────────────────────────────
async function renderBudgetSimulator() {
    const container = document.getElementById('budgetView');
    container.innerHTML = `
        <div class="card">
            <div class="card-title">What-If Budget Simulator</div>
            <label>Budget ($): <input type="range" id="budgetSlider" min="0" max="500000" step="10000" value="100000"> <span id="budgetVal">$100,000</span></label><br>
            <button id="runBudgetSim" class="btn-secondary">Optimize</button>
            <div id="budgetResults"></div>
        </div>
    `;
    const slider = document.getElementById('budgetSlider');
    const budgetVal = document.getElementById('budgetVal');
    slider.oninput = () => budgetVal.innerText = `$${parseInt(slider.value).toLocaleString()}`;
    const runBtn = document.getElementById('runBudgetSim');
    runBtn.onclick = async () => {
        const budget = parseInt(slider.value);
        const resultsDiv = document.getElementById('budgetResults');
        resultsDiv.innerHTML = '⏳ Calculating...';
        try {
            const res = await apiCall('/api/cost/optimize', 'POST', { budget_usd: budget, max_poles: 20 });
            if (res.selected_poles && res.selected_poles.length) {
                resultsDiv.innerHTML = `
                    <div><strong>Budget:</strong> $${res.budget_usd.toLocaleString()} | <strong>Remaining:</strong> $${res.remaining_budget.toLocaleString()}</div>
                    <div><strong>Total benefit (priority reduction):</strong> ${res.total_benefit.toFixed(1)} pts</div>
                    <div><strong>Total cost:</strong> $${res.total_cost.toLocaleString()}</div>
                    <div><strong>Selected poles (${res.selected_poles.length}):</strong></div>
                    <ul>${res.selected_poles.map(p => `<li>${p.pole_id} – ${p.action} – cost $${p.cost.toLocaleString()} (benefit ${p.benefit})</li>`).join('')}</ul>
                `;
            } else {
                resultsDiv.innerHTML = 'No poles can be repaired/replaced within this budget. Increase budget.';
            }
        } catch(e) {
            resultsDiv.innerHTML = `Error: ${e.message}`;
        }
    };
}

function updateRightPanel() {
    const panel = document.getElementById('rightPanel');
    if(!selectedPole) { panel.innerHTML = '<div class="card">Select a pole</div>'; return; }
    const p = selectedPole, level = getRiskLevel(p.risk_score), color = RISK_COLORS[level];
    panel.innerHTML = `<div class="card"><div class="card-title">SELECTED</div><div style="font-size:18px;font-weight:600;">${p.pole_id}</div><div>${p.district}</div><div style="font-size:36px;color:${color};">${p.risk_score}</div><div>RISK SCORE</div><div>Priority: ${p.priority_score}</div><button id="quickAI" class="btn-secondary" style="margin-top:10px;">AI Recommendation</button></div>`;
    document.getElementById('quickAI')?.addEventListener('click',()=>{ switchTab('ai'); callAI('maintenance'); });
}

// ── Add CSV Export button to header ──────────────────────────────
function addCSVButton() {
    const btn = document.createElement('button');
    btn.id = 'csvExportBtn';
    btn.className = 'btn-secondary';
    btn.innerHTML = '📥 Export CSV';
    btn.style.marginLeft = '10px';
    btn.onclick = () => window.open('/api/export/csv', '_blank');
    document.querySelector('.header-actions').appendChild(btn);
}

document.addEventListener('DOMContentLoaded', async()=>{
    await loadRegion();
    initMap();
    setupModalClose();
    addCSVButton();
    document.querySelectorAll('.tab-btn').forEach(btn=>btn.addEventListener('click',()=>switchTab(btn.dataset.tab)));
    document.getElementById('refreshBtn').addEventListener('click',()=>loadRegion(true));
    document.getElementById('filterRisk').addEventListener('change',()=>renderPoleList());
    switchTab('map');
});
if (!document.querySelector('#stormAnimationStyle')) {
    const style = document.createElement('style');
    style.id = 'stormAnimationStyle';
    style.textContent = `.storm-marker { animation: storm-pulse 1.5s ease-in-out infinite; } @keyframes storm-pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.7; transform: scale(1.3); } }`;
    document.head.appendChild(style);
}