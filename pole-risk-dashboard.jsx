import { useState, useEffect, useRef } from "react";

const WATSONX_API_KEY = "YOUR_WATSONX_API_KEY";
const WATSONX_PROJECT_ID = "YOUR_PROJECT_ID";

const MOCK_POLES = [
  { id: "DTE-7821", lat: 42.33, lng: -83.05, district: "Southwest Detroit", age: 34, material: "Wood", tilt: 14, cracks: true, rust: false, vegetation: "high", lastInspection: "2022-08-10", circuit: "C-SW-04", windExposure: "high", floodZone: "AE", soilType: "Clay" },
  { id: "DTE-4512", lat: 42.37, lng: -83.10, district: "Dearborn North", age: 12, material: "Steel", tilt: 2, cracks: false, rust: true, vegetation: "low", lastInspection: "2024-01-22", circuit: "C-DN-11", windExposure: "medium", floodZone: "X", soilType: "Loam" },
  { id: "DTE-9034", lat: 42.31, lng: -83.02, district: "Downriver", age: 47, material: "Wood", tilt: 19, cracks: true, rust: false, vegetation: "medium", lastInspection: "2021-03-15", circuit: "C-DR-02", windExposure: "high", floodZone: "AE", soilType: "Sandy" },
  { id: "DTE-3301", lat: 42.40, lng: -83.08, district: "Livonia", age: 8, material: "Composite", tilt: 1, cracks: false, rust: false, vegetation: "low", lastInspection: "2024-11-05", circuit: "C-LV-07", windExposure: "low", floodZone: "X", soilType: "Loam" },
  { id: "DTE-6678", lat: 42.35, lng: -83.15, district: "Allen Park", age: 29, material: "Wood", tilt: 8, cracks: false, rust: true, vegetation: "medium", lastInspection: "2023-04-30", circuit: "C-AP-03", windExposure: "medium", floodZone: "B", soilType: "Clay" },
  { id: "DTE-2290", lat: 42.28, lng: -83.07, district: "Wyandotte", age: 52, material: "Wood", tilt: 22, cracks: true, rust: true, vegetation: "high", lastInspection: "2020-06-18", circuit: "C-WY-01", windExposure: "high", floodZone: "AE", soilType: "Clay" },
  { id: "DTE-5544", lat: 42.42, lng: -83.00, district: "Hamtramck", age: 18, material: "Steel", tilt: 4, cracks: false, rust: false, vegetation: "low", lastInspection: "2024-07-14", circuit: "C-HM-09", windExposure: "low", floodZone: "X", soilType: "Loam" },
  { id: "DTE-8812", lat: 42.34, lng: -83.18, district: "Inkster", age: 41, material: "Wood", tilt: 11, cracks: true, rust: true, vegetation: "high", lastInspection: "2021-11-22", circuit: "C-IK-05", windExposure: "high", floodZone: "AE", soilType: "Clay" },
];

function computeRiskScore(pole) {
  let score = 0;
  score += Math.min(pole.age * 1.2, 40);
  score += pole.tilt * 1.8;
  if (pole.cracks) score += 15;
  if (pole.rust) score += 10;
  if (pole.vegetation === "high") score += 12;
  else if (pole.vegetation === "medium") score += 6;
  if (pole.windExposure === "high") score += 10;
  else if (pole.windExposure === "medium") score += 5;
  if (pole.floodZone === "AE") score += 8;
  else if (pole.floodZone === "B") score += 3;
  if (pole.material === "Wood") score += 8;
  const yearsSince = (new Date() - new Date(pole.lastInspection)) / (1000 * 60 * 60 * 24 * 365);
  score += Math.min(yearsSince * 3, 12);
  const rawScore = Math.min(Math.round(score), 100);
  const stormFailProb = Math.min(rawScore / 100 * 0.85 + 0.05, 0.95);
  const remainingLife = Math.max(0.5, (100 - rawScore) / 10);
  const replaceCost = pole.material === "Steel" ? 8500 : pole.material === "Composite" ? 11000 : 6200;
  const repairCost = Math.round(replaceCost * 0.35);
  return { riskScore: rawScore, stormFailProb: parseFloat(stormFailProb.toFixed(2)), remainingLife: parseFloat(remainingLife.toFixed(1)), replaceCost, repairCost };
}

const COMPUTED_POLES = MOCK_POLES.map(p => ({ ...p, ...computeRiskScore(p) }));

function getRiskLevel(score) {
  if (score >= 70) return { label: "Critical", color: "#E24B4A", bg: "#FCEBEB", textColor: "#A32D2D" };
  if (score >= 45) return { label: "High", color: "#EF9F27", bg: "#FAEEDA", textColor: "#854F0B" };
  if (score >= 25) return { label: "Medium", color: "#378ADD", bg: "#E6F1FB", textColor: "#185FA5" };
  return { label: "Low", color: "#639922", bg: "#EAF3DE", textColor: "#3B6D11" };
}

const NOAA_DATA = {
  windSpeed: 58,
  gustSpeed: 74,
  precipIn: 2.3,
  stormAlert: "WIND ADVISORY",
  stormDate: "May 17–18, 2026"
};

export default function App() {
  const [selectedPole, setSelectedPole] = useState(null);
  const [stormMode, setStormMode] = useState(false);
  const [aiResponse, setAiResponse] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [filterRisk, setFilterRisk] = useState("all");
  const [activeTab, setActiveTab] = useState("map");
  const [uploadedImage, setUploadedImage] = useState(null);
  const [cvResult, setCvResult] = useState(null);
  const [cvLoading, setCvLoading] = useState(false);
  const [imageBase64, setImageBase64] = useState(null);
  const fileInputRef = useRef();

  const filteredPoles = COMPUTED_POLES.filter(p => {
    if (filterRisk === "all") return true;
    const level = getRiskLevel(p.riskScore).label.toLowerCase();
    return level === filterRisk;
  });

  const criticalCount = COMPUTED_POLES.filter(p => p.riskScore >= 70).length;
  const highCount = COMPUTED_POLES.filter(p => p.riskScore >= 45 && p.riskScore < 70).length;
  const avgRisk = Math.round(COMPUTED_POLES.reduce((a, b) => a + b.riskScore, 0) / COMPUTED_POLES.length);

  async function callWatsonx(prompt) {
    setAiLoading(true);
    setAiResponse("");
    try {
      const response = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 1000,
          system: "You are an AI maintenance decision engine for DTE Energy, acting as IBM watsonx.ai Granite. You analyze utility pole condition data and provide structured maintenance recommendations. Be concise, practical, and field-crew-friendly. Always end with a priority action and estimated cost.",
          messages: [{ role: "user", content: prompt }]
        })
      });
      const data = await response.json();
      const text = data.content?.filter(b => b.type === "text").map(b => b.text).join("\n") || "No response.";
      setAiResponse(text);
    } catch (e) {
      setAiResponse("⚠️ Unable to connect to watsonx.ai. Check API configuration.");
    }
    setAiLoading(false);
  }

  async function analyzeWithCV(base64, pole) {
    setCvLoading(true);
    setCvResult(null);
    try {
      const imageContent = base64
        ? [{ type: "image", source: { type: "base64", media_type: "image/jpeg", data: base64 } }, { type: "text", text: "Analyze this utility pole image for structural defects. Return ONLY a JSON object with these fields: tilt_angle (number, degrees), crack_detected (boolean), rust_detected (boolean), vegetation_risk (\"low\"|\"medium\"|\"high\"), wire_sagging (boolean), overall_condition (\"good\"|\"fair\"|\"poor\"|\"critical\"), confidence (number 0-1), notes (string, max 30 words). No markdown, no preamble." }]
        : [{ type: "text", text: `Simulate a computer vision analysis for a ${pole?.age || 30}-year-old ${pole?.material || "wood"} utility pole with tilt ${pole?.tilt || 10} degrees and ${pole?.vegetation || "medium"} vegetation. Return ONLY a JSON object with: tilt_angle, crack_detected, rust_detected, vegetation_risk, wire_sagging, overall_condition, confidence, notes. No markdown.` }];
      const response = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 500,
          messages: [{ role: "user", content: imageContent }]
        })
      });
      const data = await response.json();
      const text = data.content?.filter(b => b.type === "text").map(b => b.text).join("") || "{}";
      const clean = text.replace(/```json|```/g, "").trim();
      const parsed = JSON.parse(clean);
      setCvResult(parsed);
    } catch (e) {
      setCvResult({ error: "CV analysis failed. Check image format.", notes: "" });
    }
    setCvLoading(false);
  }

  function handlePoleSelect(pole) {
    setSelectedPole(pole);
    setAiResponse("");
    setCvResult(null);
    setUploadedImage(null);
    setActiveTab("detail");
  }

  function getWatsonxPrompt(pole) {
    const risk = getRiskLevel(pole.riskScore);
    return `Pole ID: ${pole.id} | District: ${pole.district} | Material: ${pole.material} | Age: ${pole.age} years
Risk Score: ${pole.riskScore}/100 (${risk.label}) | Tilt: ${pole.tilt}° | Cracks: ${pole.cracks} | Rust: ${pole.rust}
Vegetation Risk: ${pole.vegetation} | Storm Failure Probability: ${(pole.stormFailProb * 100).toFixed(0)}% | Remaining Life: ${pole.remainingLife} years
Wind Exposure: ${pole.windExposure} | Flood Zone: ${pole.floodZone} | NOAA Alert: ${NOAA_DATA.stormAlert} with ${NOAA_DATA.windSpeed}mph winds on ${NOAA_DATA.stormDate}
Last Inspection: ${pole.lastInspection} | Circuit: ${pole.circuit}

Provide: 1) Maintenance recommendation (replace/repair/monitor) with justification. 2) Priority timeline. 3) Cost estimate for Michigan labor+materials. 4) Field crew safety notes. 5) One-line summary for dispatcher.`;
  }

  function getStormPrompt() {
    const criticalPoles = COMPUTED_POLES.filter(p => p.riskScore >= 70);
    return `STORM SIMULATION — ${NOAA_DATA.stormAlert}: ${NOAA_DATA.windSpeed}mph winds, gusts to ${NOAA_DATA.gustSpeed}mph, ${NOAA_DATA.precipIn}" rain. Date: ${NOAA_DATA.stormDate}. Region: Metro Detroit / DTE Energy Territory.

HIGH-RISK POLES LIKELY TO FAIL:
${criticalPoles.map(p => `- ${p.id} (${p.district}): Risk ${p.riskScore}, Tilt ${p.tilt}°, Fail Prob ${(p.stormFailProb * 100).toFixed(0)}%`).join("\n")}

Provide: 1) Which poles will likely fail first and why. 2) Estimated customers affected. 3) Pre-storm crew deployment recommendation. 4) Post-storm inspection priority order. 5) Total estimated emergency response cost.`;
  }

  function handleImageUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    setUploadedImage(url);
    const reader = new FileReader();
    reader.onload = (ev) => {
      const base64 = ev.target.result.split(",")[1];
      setImageBase64(base64);
    };
    reader.readAsDataURL(file);
  }

  const MapDot = ({ pole }) => {
    const risk = getRiskLevel(pole.riskScore);
    const x = ((pole.lng - (-83.20)) / ((-82.95) - (-83.20))) * 540 + 40;
    const y = ((42.45 - pole.lat) / (42.45 - 42.25)) * 280 + 30;
    const isStormFail = stormMode && pole.riskScore >= 60;
    return (
      <g onClick={() => handlePoleSelect(pole)} style={{ cursor: "pointer" }}>
        {isStormFail && (
          <circle cx={x} cy={y} r={18} fill="#E24B4A" opacity={0.25}>
            <animate attributeName="r" values="14;22;14" dur="1.5s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.25;0.05;0.25" dur="1.5s" repeatCount="indefinite" />
          </circle>
        )}
        <circle
          cx={x} cy={y} r={selectedPole?.id === pole.id ? 10 : 7}
          fill={isStormFail ? "#E24B4A" : risk.color}
          stroke={selectedPole?.id === pole.id ? "#fff" : "transparent"}
          strokeWidth={2}
        />
        {pole.riskScore >= 70 && (
          <text x={x} y={y + 1} textAnchor="middle" dominantBaseline="middle" fill="#fff" fontSize={9} fontWeight="bold">!</text>
        )}
      </g>
    );
  };

  const conditionColor = (val) => val ? "#E24B4A" : "#639922";

  return (
    <div style={{ fontFamily: "'IBM Plex Mono', 'Courier New', monospace", background: "var(--color-background-tertiary)", minHeight: "100vh", padding: "0" }}>
      <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet" />

      {/* Header */}
      <div style={{ background: "#0F1923", borderBottom: "2px solid #1D9E75", padding: "14px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 36, height: 36, background: "#1D9E75", borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="2" x2="12" y2="22" />
              <line x1="8" y1="6" x2="16" y2="6" />
              <line x1="7" y1="11" x2="17" y2="11" />
              <line x1="9" y1="16" x2="15" y2="16" />
            </svg>
          </div>
          <div>
            <div style={{ color: "#fff", fontFamily: "'IBM Plex Sans', sans-serif", fontWeight: 600, fontSize: 15, letterSpacing: "0.02em" }}>GRIDWATCH AI</div>
            <div style={{ color: "#1D9E75", fontSize: 10, letterSpacing: "0.12em" }}>DTE ENERGY · UTILITY POLE RISK PROFILING</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ background: stormMode ? "#A32D2D" : "#0F2A1F", border: `1px solid ${stormMode ? "#E24B4A" : "#1D9E75"}`, borderRadius: 4, padding: "6px 14px", cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }} onClick={() => { setStormMode(!stormMode); if (!stormMode) setAiResponse(""); }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={stormMode ? "#F09595" : "#5DCAA5"} strokeWidth="2.5"><path d="M19 16.9A5 5 0 0 0 18 7h-1.26a8 8 0 1 0-11.62 9" /><polyline points="13 11 9 17 15 17 11 23" /></svg>
            <span style={{ color: stormMode ? "#F09595" : "#5DCAA5", fontSize: 11, fontWeight: 600, letterSpacing: "0.08em" }}>{stormMode ? "STORM MODE ON" : "STORM MODE"}</span>
          </div>
          <div style={{ background: "#0F2A1F", border: "1px solid #1D9E75", borderRadius: 4, padding: "6px 14px" }}>
            <span style={{ color: "#5DCAA5", fontSize: 11, letterSpacing: "0.08em" }}>POWERED BY watsonx.ai</span>
          </div>
        </div>
      </div>

      {/* Storm Banner */}
      {stormMode && (
        <div style={{ background: "#501313", borderBottom: "1px solid #E24B4A", padding: "8px 24px", display: "flex", alignItems: "center", gap: 16 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="#F09595" stroke="#F09595" strokeWidth="1"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" stroke="#fff" strokeWidth="2" /><line x1="12" y1="17" x2="12.01" y2="17" stroke="#fff" strokeWidth="2" /></svg>
          <span style={{ color: "#F09595", fontSize: 12, fontWeight: 600, letterSpacing: "0.06em" }}>⚡ {NOAA_DATA.stormAlert} — {NOAA_DATA.stormDate} · {NOAA_DATA.windSpeed}mph sustained / {NOAA_DATA.gustSpeed}mph gusts · {NOAA_DATA.precipIn}" precipitation expected</span>
          <button onClick={() => { setActiveTab("map"); callWatsonx(getStormPrompt()); }} style={{ marginLeft: "auto", background: "#791F1F", border: "1px solid #E24B4A", color: "#F09595", fontSize: 11, padding: "4px 12px", borderRadius: 4, cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.06em" }}>RUN STORM ANALYSIS ↗</button>
        </div>
      )}

      {/* Metric Bar */}
      <div style={{ background: "#0F1923", borderBottom: "1px solid #1a2e3b", padding: "12px 24px", display: "flex", gap: 24 }}>
        {[
          { label: "TOTAL POLES", value: COMPUTED_POLES.length, color: "#5DCAA5" },
          { label: "CRITICAL RISK", value: criticalCount, color: "#E24B4A" },
          { label: "HIGH RISK", value: highCount, color: "#EF9F27" },
          { label: "AVG RISK SCORE", value: `${avgRisk}/100`, color: avgRisk >= 50 ? "#EF9F27" : "#5DCAA5" },
          { label: "STORM EXPOSURE", value: stormMode ? `${COMPUTED_POLES.filter(p => p.riskScore >= 60).length} AT RISK` : "OFF", color: stormMode ? "#E24B4A" : "#444" },
        ].map(m => (
          <div key={m.label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em" }}>{m.label}</span>
            <span style={{ color: m.color, fontSize: 18, fontWeight: 600 }}>{m.value}</span>
          </div>
        ))}
      </div>

      {/* Main Content */}
      <div style={{ display: "flex", height: "calc(100vh - 180px)", minHeight: 600 }}>

        {/* Left Panel — Pole List */}
        <div style={{ width: 260, background: "#0A1520", borderRight: "1px solid #1a2e3b", display: "flex", flexDirection: "column", flexShrink: 0 }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid #1a2e3b" }}>
            <select value={filterRisk} onChange={e => setFilterRisk(e.target.value)} style={{ width: "100%", background: "#0F1923", border: "1px solid #1a2e3b", color: "#5DCAA5", padding: "6px 8px", borderRadius: 4, fontSize: 11, fontFamily: "inherit", letterSpacing: "0.06em" }}>
              <option value="all">ALL POLES ({COMPUTED_POLES.length})</option>
              <option value="critical">CRITICAL ({criticalCount})</option>
              <option value="high">HIGH ({highCount})</option>
              <option value="medium">MEDIUM</option>
              <option value="low">LOW</option>
            </select>
          </div>
          <div style={{ overflowY: "auto", flex: 1 }}>
            {filteredPoles.sort((a, b) => b.riskScore - a.riskScore).map(pole => {
              const risk = getRiskLevel(pole.riskScore);
              const isSelected = selectedPole?.id === pole.id;
              return (
                <div key={pole.id} onClick={() => handlePoleSelect(pole)} style={{ padding: "12px 16px", borderBottom: "1px solid #1a2e3b", cursor: "pointer", background: isSelected ? "#0F2A1F" : "transparent", borderLeft: isSelected ? "2px solid #1D9E75" : "2px solid transparent", transition: "all 0.15s" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                    <span style={{ color: isSelected ? "#5DCAA5" : "#8aacb8", fontSize: 12, fontWeight: 500 }}>{pole.id}</span>
                    <span style={{ background: risk.bg, color: risk.textColor, fontSize: 9, padding: "2px 7px", borderRadius: 3, fontWeight: 600, letterSpacing: "0.06em", fontFamily: "'IBM Plex Sans', sans-serif" }}>{risk.label}</span>
                  </div>
                  <div style={{ color: "#4a6070", fontSize: 10 }}>{pole.district}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                    <div style={{ flex: 1, height: 3, background: "#1a2e3b", borderRadius: 2 }}>
                      <div style={{ width: `${pole.riskScore}%`, height: "100%", background: risk.color, borderRadius: 2 }} />
                    </div>
                    <span style={{ color: risk.color, fontSize: 11, fontWeight: 600, minWidth: 28 }}>{pole.riskScore}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Center — Map + Detail tabs */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Tab Bar */}
          <div style={{ background: "#0A1520", borderBottom: "1px solid #1a2e3b", display: "flex", padding: "0 16px", gap: 0 }}>
            {[["map", "MAP VIEW"], ["detail", "POLE DETAIL"], ["cv", "CV INSPECTION"], ["report", "AI REPORT"]].map(([key, label]) => (
              <button key={key} onClick={() => setActiveTab(key)} style={{ background: "transparent", border: "none", borderBottom: activeTab === key ? "2px solid #1D9E75" : "2px solid transparent", color: activeTab === key ? "#5DCAA5" : "#4a6070", padding: "10px 16px", fontSize: 10, fontFamily: "inherit", letterSpacing: "0.1em", cursor: "pointer", fontWeight: activeTab === key ? 600 : 400 }}>{label}</button>
            ))}
          </div>

          {/* MAP TAB */}
          {activeTab === "map" && (
            <div style={{ flex: 1, position: "relative", background: "#0A1520", overflow: "hidden" }}>
              <svg width="100%" height="100%" viewBox="0 0 620 340" style={{ display: "block" }}>
                {/* Grid lines */}
                {[0,1,2,3,4].map(i => <line key={i} x1={40 + i*135} y1={30} x2={40 + i*135} y2={310} stroke="#1a2e3b" strokeWidth={0.5} />)}
                {[0,1,2,3].map(i => <line key={i} x1={40} y1={30 + i*70} x2={580} y2={30 + i*70} stroke="#1a2e3b" strokeWidth={0.5} />)}
                {/* Road-like lines */}
                <line x1={80} y1={30} x2={320} y2={310} stroke="#1a2e3b" strokeWidth={1.5} />
                <line x1={40} y1={160} x2={580} y2={160} stroke="#1a2e3b" strokeWidth={1.5} />
                <line x1={310} y1={30} x2={310} y2={310} stroke="#1a2e3b" strokeWidth={1.5} />
                {/* District labels */}
                <text x={100} y={55} fill="#1a2e3b" fontSize={9} letterSpacing="2">DEARBORN</text>
                <text x={400} y={200} fill="#1a2e3b" fontSize={9} letterSpacing="2">DETROIT</text>
                <text x={80} y={200} fill="#1a2e3b" fontSize={9} letterSpacing="2">ALLEN PARK</text>
                <text x={350} y={290} fill="#1a2e3b" fontSize={9} letterSpacing="2">WYANDOTTE</text>
                {COMPUTED_POLES.map(pole => <MapDot key={pole.id} pole={pole} />)}
                {/* Legend */}
                <rect x={470} y={20} width={120} height={80} fill="#0F1923" rx={4} />
                <text x={480} y={36} fill="#4a6070" fontSize={8} letterSpacing="2">RISK LEVEL</text>
                {[["Critical", "#E24B4A"], ["High", "#EF9F27"], ["Medium", "#378ADD"], ["Low", "#639922"]].map(([l, c], i) => (
                  <g key={l}>
                    <circle cx={485} cy={48 + i * 14} r={4} fill={c} />
                    <text x={494} y={52 + i * 14} fill="#8aacb8" fontSize={9}>{l}</text>
                  </g>
                ))}
              </svg>
              <div style={{ position: "absolute", bottom: 16, right: 16, background: "#0F1923", border: "1px solid #1a2e3b", borderRadius: 4, padding: "8px 12px" }}>
                <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.1em", marginBottom: 4 }}>NOAA WEATHER</div>
                <div style={{ color: "#EF9F27", fontSize: 11, fontWeight: 600 }}>{NOAA_DATA.windSpeed}mph · {NOAA_DATA.precipIn}"</div>
                <div style={{ color: "#4a6070", fontSize: 9 }}>Metro Detroit</div>
              </div>
            </div>
          )}

          {/* DETAIL TAB */}
          {activeTab === "detail" && selectedPole && (
            <div style={{ flex: 1, overflowY: "auto", padding: 20, background: "#0A1520" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
                {/* Identity */}
                <div style={{ background: "#0F1923", border: "1px solid #1a2e3b", borderRadius: 6, padding: 16, gridColumn: "span 2" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <div style={{ color: "#5DCAA5", fontSize: 18, fontWeight: 600 }}>{selectedPole.id}</div>
                      <div style={{ color: "#4a6070", fontSize: 11, marginTop: 2 }}>{selectedPole.district} · Circuit {selectedPole.circuit}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 32, fontWeight: 600, color: getRiskLevel(selectedPole.riskScore).color }}>{selectedPole.riskScore}</div>
                      <div style={{ color: "#4a6070", fontSize: 10, letterSpacing: "0.08em" }}>RISK SCORE</div>
                    </div>
                  </div>
                  <div style={{ height: 4, background: "#1a2e3b", borderRadius: 2, marginTop: 12 }}>
                    <div style={{ width: `${selectedPole.riskScore}%`, height: "100%", background: getRiskLevel(selectedPole.riskScore).color, borderRadius: 2, transition: "width 0.5s" }} />
                  </div>
                </div>

                {/* Condition */}
                <div style={{ background: "#0F1923", border: "1px solid #1a2e3b", borderRadius: 6, padding: 16 }}>
                  <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em", marginBottom: 12 }}>STRUCTURAL CONDITION</div>
                  {[
                    ["Material", selectedPole.material],
                    ["Age", `${selectedPole.age} years`],
                    ["Tilt Angle", `${selectedPole.tilt}°`],
                    ["Cracks", selectedPole.cracks ? "DETECTED" : "NONE"],
                    ["Rust", selectedPole.rust ? "DETECTED" : "NONE"],
                    ["Vegetation", selectedPole.vegetation.toUpperCase()],
                  ].map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid #1a2e3b" }}>
                      <span style={{ color: "#4a6070", fontSize: 11 }}>{k}</span>
                      <span style={{ color: v === "DETECTED" ? "#E24B4A" : v === "NONE" ? "#639922" : "#8aacb8", fontSize: 11, fontWeight: 500 }}>{v}</span>
                    </div>
                  ))}
                </div>

                {/* Environment */}
                <div style={{ background: "#0F1923", border: "1px solid #1a2e3b", borderRadius: 6, padding: 16 }}>
                  <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em", marginBottom: 12 }}>ENVIRONMENT & RISK</div>
                  {[
                    ["Storm Fail Prob.", `${(selectedPole.stormFailProb * 100).toFixed(0)}%`],
                    ["Remaining Life", `${selectedPole.remainingLife} yrs`],
                    ["Wind Exposure", selectedPole.windExposure.toUpperCase()],
                    ["Flood Zone", selectedPole.floodZone],
                    ["Soil Type", selectedPole.soilType],
                    ["Last Inspect.", selectedPole.lastInspection],
                  ].map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid #1a2e3b" }}>
                      <span style={{ color: "#4a6070", fontSize: 11 }}>{k}</span>
                      <span style={{ color: "#8aacb8", fontSize: 11, fontWeight: 500 }}>{v}</span>
                    </div>
                  ))}
                </div>

                {/* Cost */}
                <div style={{ background: "#0F1923", border: "1px solid #1a2e3b", borderRadius: 6, padding: 16, gridColumn: "span 2" }}>
                  <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em", marginBottom: 12 }}>COST ESTIMATION (MICHIGAN LABOR + MATERIALS)</div>
                  <div style={{ display: "flex", gap: 24 }}>
                    <div>
                      <div style={{ color: "#E24B4A", fontSize: 22, fontWeight: 600 }}>${selectedPole.replaceCost.toLocaleString()}</div>
                      <div style={{ color: "#4a6070", fontSize: 10 }}>Full Replacement</div>
                    </div>
                    <div>
                      <div style={{ color: "#EF9F27", fontSize: 22, fontWeight: 600 }}>${selectedPole.repairCost.toLocaleString()}</div>
                      <div style={{ color: "#4a6070", fontSize: 10 }}>Repair / Reinforce</div>
                    </div>
                    <div style={{ marginLeft: "auto", display: "flex", alignItems: "center" }}>
                      <div style={{ background: getRiskLevel(selectedPole.riskScore).riskScore >= 70 ? "#501313" : "#0F2A1F", border: `1px solid ${getRiskLevel(selectedPole.riskScore).color}`, borderRadius: 4, padding: "8px 16px", color: getRiskLevel(selectedPole.riskScore).color, fontSize: 11, fontWeight: 600, letterSpacing: "0.06em" }}>
                        {selectedPole.riskScore >= 70 ? "REPLACE RECOMMENDED" : selectedPole.riskScore >= 45 ? "REPAIR OR REPLACE" : "MONITOR"}
                      </div>
                    </div>
                  </div>
                </div>

                {/* watsonx button */}
                <div style={{ gridColumn: "span 2" }}>
                  <button onClick={() => { setActiveTab("report"); callWatsonx(getWatsonxPrompt(selectedPole)); }} style={{ width: "100%", background: "#0F2A1F", border: "1px solid #1D9E75", color: "#5DCAA5", padding: "12px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit", fontSize: 12, letterSpacing: "0.08em", fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#5DCAA5" strokeWidth="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
                    GENERATE WATSONX.AI MAINTENANCE RECOMMENDATION ↗
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === "detail" && !selectedPole && (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", background: "#0A1520" }}>
              <div style={{ textAlign: "center", color: "#4a6070" }}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#1a2e3b" strokeWidth="1.5" style={{ marginBottom: 12 }}><line x1="12" y1="2" x2="12" y2="22"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="7" y1="11" x2="17" y2="11"/><line x1="9" y1="16" x2="15" y2="16"/></svg>
                <div style={{ fontSize: 12, letterSpacing: "0.1em" }}>SELECT A POLE TO VIEW DETAILS</div>
              </div>
            </div>
          )}

          {/* CV INSPECTION TAB */}
          {activeTab === "cv" && (
            <div style={{ flex: 1, overflowY: "auto", padding: 20, background: "#0A1520" }}>
              <div style={{ background: "#0F1923", border: "1px solid #1a2e3b", borderRadius: 6, padding: 20, marginBottom: 16 }}>
                <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em", marginBottom: 12 }}>COMPUTER VISION INSPECTION — UPLOAD POLE IMAGE</div>
                <div style={{ border: "2px dashed #1a2e3b", borderRadius: 6, padding: 32, textAlign: "center", cursor: "pointer" }} onClick={() => fileInputRef.current?.click()}>
                  {uploadedImage ? (
                    <img src={uploadedImage} alt="Uploaded pole" style={{ maxWidth: "100%", maxHeight: 240, borderRadius: 4, objectFit: "contain" }} />
                  ) : (
                    <>
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#1a2e3b" strokeWidth="1.5" style={{ marginBottom: 8 }}><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                      <div style={{ color: "#4a6070", fontSize: 11 }}>Click to upload pole image</div>
                      <div style={{ color: "#1a2e3b", fontSize: 10, marginTop: 4 }}>or use simulated CV for selected pole</div>
                    </>
                  )}
                  <input ref={fileInputRef} type="file" accept="image/*" style={{ display: "none" }} onChange={handleImageUpload} />
                </div>
                <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
                  <button onClick={() => analyzeWithCV(imageBase64, selectedPole)} disabled={cvLoading} style={{ flex: 1, background: "#0F2A1F", border: "1px solid #1D9E75", color: cvLoading ? "#4a6070" : "#5DCAA5", padding: "10px", borderRadius: 4, cursor: cvLoading ? "default" : "pointer", fontFamily: "inherit", fontSize: 11, letterSpacing: "0.08em" }}>
                    {cvLoading ? "⏳ ANALYZING..." : uploadedImage ? "ANALYZE UPLOADED IMAGE ↗" : "RUN SIMULATED CV ANALYSIS ↗"}
                  </button>
                </div>
              </div>

              {cvResult && !cvResult.error && (
                <div style={{ background: "#0F1923", border: "1px solid #1a2e3b", borderRadius: 6, padding: 20, marginBottom: 16 }}>
                  <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em", marginBottom: 16 }}>CV ANALYSIS RESULTS</div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
                    {[
                      ["Tilt Angle", `${cvResult.tilt_angle}°`, cvResult.tilt_angle > 10 ? "#E24B4A" : "#5DCAA5"],
                      ["Cracks Detected", cvResult.crack_detected ? "YES" : "NO", conditionColor(!cvResult.crack_detected)],
                      ["Rust Detected", cvResult.rust_detected ? "YES" : "NO", conditionColor(!cvResult.rust_detected)],
                      ["Vegetation Risk", (cvResult.vegetation_risk || "").toUpperCase(), cvResult.vegetation_risk === "high" ? "#E24B4A" : cvResult.vegetation_risk === "medium" ? "#EF9F27" : "#5DCAA5"],
                      ["Wire Sagging", cvResult.wire_sagging ? "YES" : "NO", conditionColor(!cvResult.wire_sagging)],
                      ["CV Confidence", `${Math.round((cvResult.confidence || 0) * 100)}%`, "#5DCAA5"],
                    ].map(([k, v, c]) => (
                      <div key={k} style={{ background: "#0A1520", borderRadius: 4, padding: "10px 14px" }}>
                        <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.1em", marginBottom: 4 }}>{k}</div>
                        <div style={{ color: c, fontSize: 16, fontWeight: 600 }}>{v}</div>
                      </div>
                    ))}
                  </div>
                  <div style={{ background: "#0A1520", borderRadius: 4, padding: "10px 14px", marginBottom: 12 }}>
                    <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.1em", marginBottom: 4 }}>OVERALL CONDITION</div>
                    <div style={{ color: cvResult.overall_condition === "critical" ? "#E24B4A" : cvResult.overall_condition === "poor" ? "#EF9F27" : "#5DCAA5", fontSize: 18, fontWeight: 600, textTransform: "uppercase" }}>{cvResult.overall_condition}</div>
                  </div>
                  <div style={{ color: "#8aacb8", fontSize: 11, lineHeight: 1.6, borderTop: "1px solid #1a2e3b", paddingTop: 12 }}>{cvResult.notes}</div>
                  <button onClick={() => { setActiveTab("report"); callWatsonx(`CV INSPECTION RESULT for pole ${selectedPole?.id || "unknown"}:\n${JSON.stringify(cvResult, null, 2)}\n\nBased on these computer vision findings, provide: 1) Updated risk assessment. 2) Maintenance recommendation. 3) Urgency level. 4) Field crew action items.`); }} style={{ width: "100%", marginTop: 12, background: "#0F2A1F", border: "1px solid #1D9E75", color: "#5DCAA5", padding: "10px", borderRadius: 4, cursor: "pointer", fontFamily: "inherit", fontSize: 11, letterSpacing: "0.08em" }}>
                    SEND TO WATSONX.AI FOR RECOMMENDATION ↗
                  </button>
                </div>
              )}
              {cvResult?.error && (
                <div style={{ background: "#501313", border: "1px solid #E24B4A", borderRadius: 4, padding: 12, color: "#F09595", fontSize: 11 }}>{cvResult.error}</div>
              )}
            </div>
          )}

          {/* AI REPORT TAB */}
          {activeTab === "report" && (
            <div style={{ flex: 1, overflowY: "auto", padding: 20, background: "#0A1520" }}>
              <div style={{ background: "#0F1923", border: "1px solid #1a2e3b", borderRadius: 6, padding: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
                  <div style={{ width: 8, height: 8, background: aiLoading ? "#EF9F27" : aiResponse ? "#1D9E75" : "#1a2e3b", borderRadius: "50%" }}>
                    {aiLoading && <animate attributeName="opacity" values="1;0.3;1" dur="1s" repeatCount="indefinite" />}
                  </div>
                  <span style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em" }}>WATSONX.AI · IBM GRANITE · MAINTENANCE DECISION ENGINE</span>
                </div>
                {aiLoading && (
                  <div style={{ color: "#4a6070", fontSize: 12, padding: "32px 0", textAlign: "center" }}>
                    <div style={{ marginBottom: 8 }}>⏳ Querying watsonx.ai Granite model...</div>
                    <div style={{ color: "#1a2e3b", fontSize: 10 }}>Analyzing structural data, weather exposure, and maintenance history</div>
                  </div>
                )}
                {!aiLoading && aiResponse && (
                  <div style={{ color: "#8aacb8", fontSize: 12, lineHeight: 1.8, whiteSpace: "pre-wrap", fontFamily: "'IBM Plex Sans', sans-serif" }}>{aiResponse}</div>
                )}
                {!aiLoading && !aiResponse && (
                  <div style={{ color: "#4a6070", fontSize: 11, padding: "32px 0", textAlign: "center" }}>
                    <div>Select a pole and click "Generate watsonx.ai Recommendation"</div>
                    <div style={{ marginTop: 4, fontSize: 10 }}>or run Storm Analysis from the storm mode banner</div>
                  </div>
                )}
              </div>

              {!aiLoading && aiResponse && selectedPole && (
                <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <button onClick={() => callWatsonx(`For pole ${selectedPole.id}, estimate full 5-year maintenance schedule including inspection intervals, repair milestones, and replacement planning. Format as a timeline with dates and costs.`)} style={{ background: "#0F1923", border: "1px solid #1a2e3b", color: "#8aacb8", padding: "10px", borderRadius: 4, cursor: "pointer", fontFamily: "inherit", fontSize: 10, letterSpacing: "0.06em" }}>
                    5-YEAR MAINTENANCE SCHEDULE ↗
                  </button>
                  <button onClick={() => callWatsonx(`Compare the cost-benefit of repairing vs replacing pole ${selectedPole.id} (${selectedPole.material}, ${selectedPole.age} years old, risk score ${selectedPole.riskScore}). Include NPV analysis over 10 years, downtime costs, and regulatory compliance.`)} style={{ background: "#0F1923", border: "1px solid #1a2e3b", color: "#8aacb8", padding: "10px", borderRadius: 4, cursor: "pointer", fontFamily: "inherit", fontSize: 10, letterSpacing: "0.06em" }}>
                    REPAIR vs REPLACE ANALYSIS ↗
                  </button>
                  <button onClick={() => callWatsonx(`Generate a field crew work order for pole ${selectedPole.id} in ${selectedPole.district}. Include safety checklist, tools required, estimated work hours, and permit requirements for Michigan utility work.`)} style={{ background: "#0F1923", border: "1px solid #1a2e3b", color: "#8aacb8", padding: "10px", borderRadius: 4, cursor: "pointer", fontFamily: "inherit", fontSize: 10, letterSpacing: "0.06em" }}>
                    GENERATE WORK ORDER ↗
                  </button>
                  <button onClick={() => callWatsonx(`Rank all poles in ${selectedPole.district} district for maintenance priority. Explain triage logic, estimated budget for next quarter, and recommended crew allocation.`)} style={{ background: "#0F1923", border: "1px solid #1a2e3b", color: "#8aacb8", padding: "10px", borderRadius: 4, cursor: "pointer", fontFamily: "inherit", fontSize: 10, letterSpacing: "0.06em" }}>
                    DISTRICT TRIAGE REPORT ↗
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Panel — Analytics */}
        <div style={{ width: 220, background: "#0A1520", borderLeft: "1px solid #1a2e3b", padding: 16, overflowY: "auto", flexShrink: 0 }}>
          <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em", marginBottom: 12 }}>RISK DISTRIBUTION</div>
          {[["Critical", "#E24B4A", criticalCount], ["High", "#EF9F27", highCount], ["Medium", "#378ADD", COMPUTED_POLES.filter(p => p.riskScore >= 25 && p.riskScore < 45).length], ["Low", "#639922", COMPUTED_POLES.filter(p => p.riskScore < 25).length]].map(([label, color, count]) => (
            <div key={label} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ color: "#4a6070", fontSize: 10 }}>{label}</span>
                <span style={{ color, fontSize: 10, fontWeight: 600 }}>{count}</span>
              </div>
              <div style={{ height: 3, background: "#1a2e3b", borderRadius: 2 }}>
                <div style={{ width: `${(count / COMPUTED_POLES.length) * 100}%`, height: "100%", background: color, borderRadius: 2 }} />
              </div>
            </div>
          ))}

          <div style={{ borderTop: "1px solid #1a2e3b", marginTop: 20, paddingTop: 16 }}>
            <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em", marginBottom: 12 }}>MATERIAL BREAKDOWN</div>
            {["Wood", "Steel", "Composite"].map(mat => {
              const cnt = COMPUTED_POLES.filter(p => p.material === mat).length;
              return (
                <div key={mat} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid #1a2e3b" }}>
                  <span style={{ color: "#4a6070", fontSize: 10 }}>{mat}</span>
                  <span style={{ color: "#8aacb8", fontSize: 10 }}>{cnt} poles</span>
                </div>
              );
            })}
          </div>

          <div style={{ borderTop: "1px solid #1a2e3b", marginTop: 20, paddingTop: 16 }}>
            <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em", marginBottom: 12 }}>ESTIMATED COSTS</div>
            <div style={{ marginBottom: 8 }}>
              <div style={{ color: "#4a6070", fontSize: 9 }}>All Replacements</div>
              <div style={{ color: "#E24B4A", fontSize: 14, fontWeight: 600 }}>${(COMPUTED_POLES.reduce((a, p) => a + p.replaceCost, 0) / 1000).toFixed(0)}K</div>
            </div>
            <div>
              <div style={{ color: "#4a6070", fontSize: 9 }}>Priority (Critical Only)</div>
              <div style={{ color: "#EF9F27", fontSize: 14, fontWeight: 600 }}>${(COMPUTED_POLES.filter(p => p.riskScore >= 70).reduce((a, p) => a + p.replaceCost, 0) / 1000).toFixed(0)}K</div>
            </div>
          </div>

          <div style={{ borderTop: "1px solid #1a2e3b", marginTop: 20, paddingTop: 16 }}>
            <div style={{ color: "#4a6070", fontSize: 9, letterSpacing: "0.12em", marginBottom: 8 }}>QUICK ACTIONS</div>
            <button onClick={() => { setActiveTab("report"); callWatsonx(`Generate a prioritized maintenance plan for ALL ${COMPUTED_POLES.length} poles in the Metro Detroit DTE Energy service territory. Include: top 5 most urgent poles, budget allocation for Q3 2026, crew deployment schedule, and expected risk reduction.`); }} style={{ width: "100%", background: "#0F2A1F", border: "1px solid #1D9E75", color: "#5DCAA5", padding: "8px", borderRadius: 4, cursor: "pointer", fontFamily: "inherit", fontSize: 9, letterSpacing: "0.08em", marginBottom: 8 }}>
              FULL TERRITORY REPORT ↗
            </button>
            <button onClick={() => { setStormMode(true); setActiveTab("report"); callWatsonx(getStormPrompt()); }} style={{ width: "100%", background: "#2A0F0F", border: "1px solid #E24B4A", color: "#F09595", padding: "8px", borderRadius: 4, cursor: "pointer", fontFamily: "inherit", fontSize: 9, letterSpacing: "0.08em" }}>
              STORM IMPACT ANALYSIS ↗
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
