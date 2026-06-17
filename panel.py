import sys
import json
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

sys.path.insert(0, '.')
from config.settings import CAPITAL_TOTAL_USD, TRADING_PAIRS

PANEL_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OKX Trading Bot — Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0e1a;color:#e0e6f0;font-family:'Segoe UI',sans-serif;min-height:100vh}
.header{background:#111827;padding:16px 24px;border-bottom:1px solid #1f2937;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}
.header h1{font-size:20px;color:#00d4aa;font-weight:700;display:flex;align-items:center;gap:8px}
.dot{width:8px;height:8px;border-radius:50%;background:#00d4aa;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}
.badge{padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}
.badge-real{background:#f5a62322;color:#f5a623;border:1px solid #f5a62344}
.badge-activo{background:#00d4aa22;color:#00d4aa;border:1px solid #00d4aa44}
.badge-inactivo{background:#ef444422;color:#ef4444;border:1px solid #ef444444}
.grid-4{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;padding:20px 24px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:0 24px 20px}
.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;padding:0 24px 20px}
.card{background:#111827;border-radius:12px;padding:20px;border:1px solid #1f2937}
.card-title{font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px}
.card-value{font-size:28px;font-weight:700}
.card-sub{font-size:12px;color:#6b7280;margin-top:4px}
.green{color:#00d4aa}.red{color:#ef4444}.yellow{color:#f5a623}.white{color:#fff}
.section{padding:0 24px 20px}
.section-title{font-size:13px;color:#9ca3af;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center}
.table{width:100%;border-collapse:collapse;background:#111827;border-radius:12px;overflow:hidden;border:1px solid #1f2937}
.table th{background:#1f2937;padding:10px 14px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px}
.table td{padding:12px 14px;border-top:1px solid #1f2937;font-size:13px}
.table tr:hover td{background:#1f293740}
.pill{padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
.pill-buy{background:#00d4aa22;color:#00d4aa}
.pill-sell{background:#ef444422;color:#ef4444}
.pill-win{background:#00d4aa22;color:#00d4aa}
.pill-loss{background:#ef444422;color:#ef4444}
.pill-open{background:#f5a62322;color:#f5a623}
.pill-close{background:#6b728022;color:#6b7280}
.btns{display:flex;gap:8px;padding:0 24px 20px}
.btn{padding:8px 16px;border-radius:8px;border:none;cursor:pointer;font-size:13px;font-weight:600;transition:all 0.2s}
.btn-green{background:#00d4aa22;color:#00d4aa;border:1px solid #00d4aa44}
.btn-green:hover{background:#00d4aa44}
.btn-yellow{background:#f5a62322;color:#f5a623;border:1px solid #f5a62344}
.btn-yellow:hover{background:#f5a62344}
.btn-red{background:#ef444422;color:#ef4444;border:1px solid #ef444444}
.btn-red:hover{background:#ef444444}
.btn-blue{background:#3b82f622;color:#3b82f6;border:1px solid #3b82f644}
.btn-blue:hover{background:#3b82f644}
.chart-wrap{background:#111827;border-radius:12px;border:1px solid #1f2937;padding:16px;height:180px;position:relative;overflow:hidden}
.pares-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px}
.par-card{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:12px;text-align:center}
.par-nombre{font-size:11px;color:#9ca3af;margin-bottom:4px}
.par-precio{font-size:15px;font-weight:700;color:#fff}
.par-cambio{font-size:11px;margin-top:3px}
.blacklist-badge{background:#ef444422;color:#ef4444;border:1px solid #ef444444;padding:2px 6px;border-radius:4px;font-size:10px;margin-left:4px}
.toast{position:fixed;bottom:20px;right:20px;background:#1f2937;color:#fff;padding:12px 20px;border-radius:10px;border:1px solid #374151;font-size:13px;display:none;z-index:999;box-shadow:0 4px 20px #000}
.progress-bar{height:4px;background:#1f2937;border-radius:2px;margin-top:8px;overflow:hidden}
.progress-fill{height:100%;border-radius:2px;transition:width 0.3s}
.stat-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #1f2937}
.stat-row:last-child{border-bottom:none}
.mode-selector{display:flex;gap:8px;margin-bottom:12px}
.mode-btn{padding:6px 14px;border-radius:6px;border:1px solid #374151;background:transparent;color:#6b7280;cursor:pointer;font-size:12px;font-weight:600;transition:all 0.2s}
.mode-btn.active{background:#00d4aa22;color:#00d4aa;border-color:#00d4aa44}
.tab-bar{display:flex;gap:0;border-bottom:1px solid #1f2937;margin:0 24px 16px}
.tab{padding:10px 20px;cursor:pointer;font-size:13px;color:#6b7280;border-bottom:2px solid transparent;transition:all 0.2s}
.tab.active{color:#00d4aa;border-bottom-color:#00d4aa}
.tab-content{display:none}.tab-content.active{display:block}
</style>
</head>
<body>

<div class="header">
  <h1><div class="dot" id="dot"></div> OKX Trading Bot</h1>
  <div style="display:flex;gap:8px;align-items:center">
    <span class="badge badge-real">REAL</span>
    <span class="badge" id="estado-badge">INACTIVO</span>
    <span style="color:#6b7280;font-size:12px" id="hora-update"></span>
  </div>
</div>

<!-- MÉTRICAS PRINCIPALES -->
<div class="grid-4">
  <div class="card">
    <div class="card-title">Balance Total</div>
    <div class="card-value green" id="balance-total">$0.00</div>
    <div class="card-sub" id="balance-cambio">vs capital inicial</div>
  </div>
  <div class="card">
    <div class="card-title">USDT Libre</div>
    <div class="card-value white" id="usdt-libre">$0.00</div>
    <div class="progress-bar"><div class="progress-fill" id="usdt-bar" style="background:#00d4aa;width:0%"></div></div>
  </div>
  <div class="card">
    <div class="card-title">PnL Hoy</div>
    <div class="card-value" id="pnl-hoy">+$0.00</div>
    <div class="card-sub" id="pnl-hoy-pct">0.00%</div>
  </div>
  <div class="card">
    <div class="card-title">PnL Total Acumulado</div>
    <div class="card-value" id="pnl-total">+$0.00</div>
    <div class="card-sub" id="pnl-total-pct">0.00% ROI</div>
  </div>
  <div class="card">
    <div class="card-title">Trades Hoy</div>
    <div class="card-value yellow" id="trades-hoy">0</div>
    <div class="card-sub" id="trades-sub">0 ganados / 0 perdidos</div>
  </div>
  <div class="card">
    <div class="card-title">Winrate Total</div>
    <div class="card-value" id="winrate">0%</div>
    <div class="progress-bar"><div class="progress-fill" id="winrate-bar" style="background:#00d4aa;width:0%"></div></div>
  </div>
  <div class="card">
    <div class="card-title">Posiciones Abiertas</div>
    <div class="card-value yellow" id="posiciones">0</div>
    <div class="card-sub" id="pos-valor">$0.00 en mercado</div>
  </div>
  <div class="card">
    <div class="card-title">Capital Inicial</div>
    <div class="card-value white">$87.00</div>
    <div class="card-sub">Configurado</div>
  </div>
</div>

<!-- BOTONES DE CONTROL -->
<div class="btns">
  <button class="btn btn-green" onclick="accion('iniciar')">▶ Iniciar Bot</button>
  <button class="btn btn-yellow" onclick="accion('pausar')">⏸ Pausar</button>
  <button class="btn btn-red" onclick="accion('detener')">⏹ Detener</button>
  <button class="btn btn-blue" onclick="actualizar()">🔄 Actualizar</button>
</div>

<!-- MODO DE TRADING -->
<div class="section">
  <div class="section-title">Modo de Trading</div>
  <div class="mode-selector">
    <button class="mode-btn" id="modo-conservador" onclick="cambiarModo('conservador')">🛡 Conservador (SL 1.5% / TP 2%)</button>
    <button class="mode-btn active" id="modo-normal" onclick="cambiarModo('normal')">⚖ Normal (SL 2% / TP 4%)</button>
    <button class="mode-btn" id="modo-agresivo" onclick="cambiarModo('agresivo')">🚀 Agresivo (SL 3% / TP 6%)</button>
  </div>
</div>

<!-- TABS -->
<div class="tab-bar">
  <div class="tab active" onclick="showTab('abiertas')">Posiciones Abiertas</div>
  <div class="tab" onclick="showTab('historial')">Historial Trades</div>
  <div class="tab" onclick="showTab('estadisticas')">Estadísticas</div>
  <div class="tab" onclick="showTab('mercado')">Mercado</div>
</div>

<!-- TAB: POSICIONES ABIERTAS -->
<div id="tab-abiertas" class="tab-content active section">
  <table class="table">
    <thead><tr>
      <th>Par</th><th>Entrada</th><th>Actual</th><th>Tamaño</th>
      <th>PnL $</th><th>PnL %</th><th>SL</th><th>TP</th>
      <th>Score</th><th>Estado</th><th>Tiempo</th>
    </tr></thead>
    <tbody id="tabla-abiertas">
      <tr><td colspan="11" style="text-align:center;color:#6b7280;padding:24px">Sin posiciones abiertas</td></tr>
    </tbody>
  </table>
</div>

<!-- TAB: HISTORIAL -->
<div id="tab-historial" class="tab-content section">
  <table class="table">
    <thead><tr>
      <th>Par</th><th>Resultado</th><th>Entrada</th><th>Salida</th>
      <th>PnL $</th><th>PnL %</th><th>Duración</th><th>Razón</th><th>Fecha</th>
    </tr></thead>
    <tbody id="tabla-historial">
      <tr><td colspan="9" style="text-align:center;color:#6b7280;padding:24px">Sin historial aún</td></tr>
    </tbody>
  </table>
</div>

<!-- TAB: ESTADÍSTICAS -->
<div id="tab-estadisticas" class="tab-content section">
  <div class="grid-3" style="padding:0 0 16px">
    <div class="card">
      <div class="card-title">Mejor Trade</div>
      <div class="card-value green" id="mejor-trade">$0.00</div>
    </div>
    <div class="card">
      <div class="card-title">Peor Trade</div>
      <div class="card-value red" id="peor-trade">$0.00</div>
    </div>
    <div class="card">
      <div class="card-title">Total Trades Histórico</div>
      <div class="card-value yellow" id="total-trades">0</div>
    </div>
  </div>
  <div class="card">
    <div class="card-title">Rendimiento por Par</div>
    <div id="stats-pares" style="margin-top:8px">
      <div style="color:#6b7280;font-size:13px">Sin datos aún</div>
    </div>
  </div>
  <div style="margin-top:16px" class="card">
    <div class="card-title">Pares en Blacklist</div>
    <div id="blacklist-pares" style="margin-top:8px;color:#6b7280;font-size:13px">Ninguno</div>
  </div>
</div>

<!-- TAB: MERCADO -->
<div id="tab-mercado" class="tab-content section">
  <div class="pares-grid" id="pares-mercado">
    <div style="color:#6b7280">Cargando precios...</div>
  </div>
</div>

<div style="text-align:center;padding:16px;color:#374151;font-size:12px">
  OKX Trading Bot v2.0 — Actualización automática cada 15 segundos
</div>

<div class="toast" id="toast"></div>

<script>
let modoActual = 'normal';

function showTab(tab) {
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-' + tab).classList.add('active');
}

function mostrarToast(msg, tipo='info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.background = tipo === 'error' ? '#ef444422' : '#1f2937';
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 3000);
}

async function accion(cmd) {
  try {
    const r = await fetch('/api/accion/' + cmd, {method:'POST'});
    const d = await r.json();
    mostrarToast(d.mensaje || cmd);
    setTimeout(actualizar, 1000);
  } catch(e) { mostrarToast('Error: ' + e, 'error'); }
}

async function cambiarModo(modo) {
  try {
    const r = await fetch('/api/modo/' + modo, {method:'POST'});
    const d = await r.json();
    modoActual = modo;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('modo-' + modo).classList.add('active');
    mostrarToast(d.mensaje || 'Modo cambiado: ' + modo);
  } catch(e) { mostrarToast('Error cambiando modo', 'error'); }
}

function fmt(n, dec=2) { return Number(n||0).toFixed(dec); }
function fmtUSD(n) { return '$' + fmt(n); }
function fmtPct(n) { return (n>=0?'+':'') + fmt(n) + '%'; }
function fmtSign(n) { return (n>=0?'+':'') + fmtUSD(n); }
function colorClass(n) { return n >= 0 ? 'green' : 'red'; }

async function actualizar() {
  try {
    const r = await fetch('/api/estado');
    if (!r.ok) return;
    const d = await r.json();

    document.getElementById('hora-update').textContent = 'Actualizado: ' + d.hora;

    // Balance
    document.getElementById('balance-total').textContent = fmtUSD(d.balance_total);
    const roi = ((d.balance_total - 87) / 87) * 100;
    document.getElementById('balance-cambio').textContent = fmtSign(d.balance_total - 87) + ' (' + fmtPct(roi) + ') vs $87';

    // USDT libre
    document.getElementById('usdt-libre').textContent = fmtUSD(d.usdt_libre);
    const pctLibre = (d.usdt_libre / d.balance_total) * 100;
    document.getElementById('usdt-bar').style.width = pctLibre + '%';

    // PnL hoy
    const ph = d.pnl_hoy;
    const ephEl = document.getElementById('pnl-hoy');
    ephEl.textContent = fmtSign(ph);
    ephEl.className = 'card-value ' + colorClass(ph);
    const phPct = d.balance_total > 0 ? (ph / d.balance_total) * 100 : 0;
    document.getElementById('pnl-hoy-pct').textContent = fmtPct(phPct) + ' hoy';

    // PnL total
    const pt = d.pnl_total;
    const eptEl = document.getElementById('pnl-total');
    eptEl.textContent = fmtSign(pt);
    eptEl.className = 'card-value ' + colorClass(pt);
    document.getElementById('pnl-total-pct').textContent = fmtPct(roi) + ' ROI total';

    // Trades
    document.getElementById('trades-hoy').textContent = d.trades_hoy;
    document.getElementById('trades-sub').textContent = d.ganados_hoy + ' ganados / ' + d.perdidos_hoy + ' perdidos';

    // Winrate
    const wr = d.winrate;
    const wrEl = document.getElementById('winrate');
    wrEl.textContent = wr + '%';
    wrEl.className = 'card-value ' + (wr >= 50 ? 'green' : 'red');
    document.getElementById('winrate-bar').style.width = wr + '%';
    document.getElementById('winrate-bar').style.background = wr >= 50 ? '#00d4aa' : '#ef4444';

    // Posiciones
    document.getElementById('posiciones').textContent = d.posiciones;
    const valorMercado = (d.operaciones || []).reduce((s,o) => s + (o.precio_actual * (o.tamano_usdt / o.precio_entrada) || o.tamano_usdt), 0);
    document.getElementById('pos-valor').textContent = fmtUSD(valorMercado) + ' en mercado';

    // Estado badge
    const badge = document.getElementById('estado-badge');
    const dot = document.getElementById('dot');
    if (d.activo) {
      badge.textContent = 'ACTIVO';
      badge.className = 'badge badge-activo';
      dot.style.background = '#00d4aa';
    } else {
      badge.textContent = 'INACTIVO';
      badge.className = 'badge badge-inactivo';
      dot.style.background = '#ef4444';
    }

    // Tabla posiciones abiertas
    const tbody = document.getElementById('tabla-abiertas');
    if (!d.operaciones || d.operaciones.length === 0) {
      tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:#6b7280;padding:24px">Sin posiciones abiertas</td></tr>';
    } else {
      tbody.innerHTML = d.operaciones.map(op => {
        const pnl = op.pnl_actual || 0;
        const pnlPct = op.precio_entrada > 0 ? ((op.precio_actual - op.precio_entrada) / op.precio_entrada) * 100 : 0;
        const pc = pnl >= 0 ? '#00d4aa' : '#ef4444';
        const estado = pnl > op.tamano_usdt * 0.02 ? '🔥 Ganando bien' :
                       pnl < -op.tamano_usdt * 0.015 ? '⚠️ Cerca SL' :
                       pnl > 0 ? '📈 En ganancia' : '📉 En pérdida';
        return '<tr>' +
          '<td><strong>' + op.par + '</strong></td>' +
          '<td>$' + fmt(op.precio_entrada, 4) + '</td>' +
          '<td>$' + fmt(op.precio_actual, 4) + '</td>' +
          '<td>$' + fmt(op.tamano_usdt) + '</td>' +
          '<td style="color:' + pc + '">' + fmtSign(pnl) + '</td>' +
          '<td style="color:' + pc + '">' + fmtPct(pnlPct) + '</td>' +
          '<td style="color:#ef4444">$' + fmt(op.stop_loss, 4) + '</td>' +
          '<td style="color:#00d4aa">$' + fmt(op.take_profit, 4) + '</td>' +
          '<td>' + (op.confianza || 0) + '</td>' +
          '<td>' + estado + '</td>' +
          '<td>' + (op.abierta_en || '-') + '</td>' +
        '</tr>';
      }).join('');
    }

    // Historial
    const thist = document.getElementById('tabla-historial');
    if (!d.historial || d.historial.length === 0) {
      thist.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#6b7280;padding:24px">Sin historial aún</td></tr>';
    } else {
      thist.innerHTML = d.historial.map(t => {
        const pnl = t.pnl_usdt || 0;
        const pct = t.precio_entrada > 0 ? ((t.precio_salida - t.precio_entrada) / t.precio_entrada) * 100 : 0;
        const resultado = pnl >= 0 ? '<span class="pill pill-win">GANANCIA</span>' : '<span class="pill pill-loss">PÉRDIDA</span>';
        return '<tr>' +
          '<td><strong>' + t.par + '</strong></td>' +
          '<td>' + resultado + '</td>' +
          '<td>$' + fmt(t.precio_entrada, 4) + '</td>' +
          '<td>$' + fmt(t.precio_salida, 4) + '</td>' +
          '<td style="color:' + (pnl>=0?'#00d4aa':'#ef4444') + '">' + fmtSign(pnl) + '</td>' +
          '<td style="color:' + (pct>=0?'#00d4aa':'#ef4444') + '">' + fmtPct(pct) + '</td>' +
          '<td>' + (t.duracion_min || 0) + ' min</td>' +
          '<td style="color:#6b7280;font-size:11px">' + (t.razon_salida || '-') + '</td>' +
          '<td>' + (t.cerrada_en || '-') + '</td>' +
        '</tr>';
      }).join('');
    }

    // Estadísticas
    if (d.stats) {
      document.getElementById('mejor-trade').textContent = fmtUSD(d.stats.mejor_trade || 0);
      document.getElementById('peor-trade').textContent = fmtUSD(d.stats.peor_trade || 0);
      document.getElementById('total-trades').textContent = d.stats.total_trades || 0;
    }

    // Blacklist
    const bl = document.getElementById('blacklist-pares');
    if (d.blacklist && d.blacklist.length > 0) {
      bl.innerHTML = d.blacklist.map(p => '<span class="blacklist-badge">' + p + '</span>').join(' ');
    } else {
      bl.textContent = 'Ninguno — todos los pares activos';
    }

    // Mercado
    const pg = document.getElementById('pares-mercado');
    if (d.precios && d.precios.length > 0) {
      pg.innerHTML = d.precios.map(p => {
        const bl = d.blacklist && d.blacklist.includes(p.par);
        return '<div class="par-card" style="' + (bl ? 'opacity:0.5;border-color:#ef4444' : '') + '">' +
          '<div class="par-nombre">' + p.par + (bl ? '<span class="blacklist-badge">BL</span>' : '') + '</div>' +
          '<div class="par-precio">$' + Number(p.precio).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:4}) + '</div>' +
          '<div class="par-cambio ' + (p.cambio>=0?'green':'red') + '">' + (p.cambio>=0?'▲':'▼') + ' ' + Math.abs(p.cambio).toFixed(2) + '%</div>' +
        '</div>';
      }).join('');
    }

  } catch(e) { console.error('Error:', e); }
}

actualizar();
setInterval(actualizar, 15000);
</script>
</body>
</html>"""

estado_panel = {
    "motor": None,
    "okx":   None,
    "precios": [],
    "modo": "normal",
    "blacklist": [],
}

MODOS = {
    "conservador": {"stop": 0.015, "tp": 0.02,  "trailing": 0.01},
    "normal":      {"stop": 0.02,  "tp": 0.04,  "trailing": 0.015},
    "agresivo":    {"stop": 0.03,  "tp": 0.06,  "trailing": 0.02},
}


def actualizar_precios_cache():
    import time
    while True:
        try:
            okx = estado_panel.get("okx")
            if okx:
                precios = []
                for par in TRADING_PAIRS:
                    try:
                        precio = okx.get_price(par)
                        stats  = okx.get_24h_stats(par)
                        cambio = stats.get("cambio_24h", 0.0) if stats else 0.0
                        if precio > 0:
                            precios.append({"par": par, "precio": float(precio), "cambio": float(cambio)})
                    except Exception:
                        pass
                estado_panel["precios"] = precios
        except Exception:
            pass
        time.sleep(30)


class PanelHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        try:
            if self.path.startswith('/api/accion/'):
                cmd   = self.path.split('/')[-1]
                motor = estado_panel.get("motor")
                msg   = "OK"

                if cmd == "iniciar" and motor and not motor.activo:
                    import asyncio
                    t = threading.Thread(
                        target=lambda: asyncio.new_event_loop().run_until_complete(motor.iniciar()),
                        daemon=True
                    )
                    t.start()
                    msg = "Bot iniciado"
                elif cmd == "pausar" and motor:
                    motor.detener()
                    msg = "Bot pausado"
                elif cmd == "detener" and motor:
                    motor.detener()
                    msg = "Bot detenido"

                resp = json.dumps({"ok": True, "mensaje": msg}).encode()
                self._json(resp)

            elif self.path.startswith('/api/modo/'):
                modo  = self.path.split('/')[-1]
                motor = estado_panel.get("motor")
                if modo in MODOS and motor:
                    cfg = MODOS[modo]
                    import config.settings as s
                    s.STOP_LOSS_PCT   = cfg["stop"]
                    s.TAKE_PROFIT_PCT = cfg["tp"]
                    s.TRAILING_PCT    = cfg["trailing"]
                    estado_panel["modo"] = modo
                    msg = f"Modo {modo}: SL {cfg['stop']*100:.1f}% / TP {cfg['tp']*100:.1f}%"
                else:
                    msg = "Modo no reconocido"
                self._json(json.dumps({"ok": True, "mensaje": msg}).encode())
        except Exception:
            pass

    def _json(self, content):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        try:
            if self.path == '/':
                contenido = PANEL_HTML.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(contenido))
                self.end_headers()
                self.wfile.write(contenido)

            elif self.path == '/api/estado':
                motor = estado_panel.get("motor")
                okx   = estado_panel.get("okx")

                usdt_libre    = 0.0
                balance_total = 0.0
                pnl_hoy       = 0.0
                pnl_total     = 0.0
                trades_hoy    = 0
                ganados_hoy   = 0
                perdidos_hoy  = 0
                activo        = False
                ops           = []
                db            = None

                try:
                    if okx:
                        usdt_libre    = okx.get_balance()
                        balance_total = okx.get_total_balance_usdt()
                    if motor:
                        pnl_hoy      = motor.pnl_hoy
                        pnl_total    = motor.pnl_total
                        trades_hoy   = motor.trades_hoy
                        ganados_hoy  = motor.trades_ganados
                        perdidos_hoy = motor.trades_perdidos
                        activo       = motor.activo
                        ops          = motor.operaciones
                        db           = motor.db
                except Exception:
                    pass

                total = ganados_hoy + perdidos_hoy
                winrate = int((ganados_hoy / total) * 100) if total > 0 else 0

                ops_data = []
                for op in ops:
                    try:
                        precio_actual = okx.get_price(op["par"]) if okx else 0.0
                        pnl_pct = (precio_actual - op["precio_entrada"]) / op["precio_entrada"] * 100 if op["precio_entrada"] > 0 else 0
                        ops_data.append({
                            "par":            op["par"],
                            "precio_entrada": float(op["precio_entrada"]),
                            "precio_actual":  float(precio_actual),
                            "tamano_usdt":    float(op["tamaño_usdt"]),
                            "pnl_actual":     float(op.get("pnl_actual", 0)),
                            "stop_loss":      float(op["stop_loss"]),
                            "take_profit":    float(op["take_profit"]),
                            "confianza":      int(op.get("confianza", 0)),
                            "abierta_en":     op["abierta_en"].strftime("%d/%m %H:%M"),
                        })
                    except Exception:
                        pass

                historial = []
                stats     = {}
                if db:
                    try:
                        for t in db.get_trades_historial(30):
                            historial.append({
                                "par":           t.par,
                                "precio_entrada": float(t.precio_entrada or 0),
                                "precio_salida":  float(t.precio_salida or 0),
                                "pnl_usdt":       float(t.pnl_usdt or 0),
                                "duracion_min":   int(t.duracion_min or 0),
                                "razon_salida":   t.razon_salida or "-",
                                "cerrada_en":     t.cerrada_en.strftime("%d/%m %H:%M") if t.cerrada_en else "-",
                            })
                        stats = db.get_estadisticas()
                    except Exception:
                        pass

                blacklist = []
                if motor and hasattr(motor, 'blacklist'):
                    blacklist = list(motor.blacklist.keys())

                data = {
                    "activo":        activo,
                    "usdt_libre":    float(usdt_libre),
                    "balance_total": float(balance_total),
                    "pnl_hoy":       float(pnl_hoy),
                    "pnl_total":     float(pnl_total),
                    "trades_hoy":    int(trades_hoy),
                    "ganados_hoy":   int(ganados_hoy),
                    "perdidos_hoy":  int(perdidos_hoy),
                    "winrate":       int(winrate),
                    "posiciones":    len(ops_data),
                    "operaciones":   ops_data,
                    "historial":     historial,
                    "stats":         stats,
                    "precios":       estado_panel["precios"],
                    "blacklist":     blacklist,
                    "modo":          estado_panel["modo"],
                    "hora":          datetime.now().strftime("%H:%M:%S"),
                }

                contenido = json.dumps(data).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', len(contenido))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(contenido)
            else:
                self.send_response(404)
                self.end_headers()
        except Exception:
            pass


def iniciar_panel(motor=None, okx=None, puerto=8080):
    estado_panel["motor"] = motor
    estado_panel["okx"]   = okx

    threading.Thread(target=actualizar_precios_cache, daemon=True).start()

    servidor = HTTPServer(('0.0.0.0', puerto), PanelHandler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    print(f"[OK] Panel web iniciado en http://localhost:{puerto}")
    return servidor