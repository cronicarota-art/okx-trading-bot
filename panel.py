import sys
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

sys.path.insert(0, '.')
from config.settings import CAPITAL_TOTAL_USD, TRADING_PAIRS

PANEL_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OKX Trading Bot</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0e1a;color:#e0e6f0;font-family:'Segoe UI',sans-serif}
.header{background:#111827;padding:20px 30px;border-bottom:1px solid #1f2937;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:22px;color:#00d4aa;font-weight:700}
.badge{background:#f5a62322;color:#f5a623;padding:4px 12px;border-radius:20px;font-size:13px;border:1px solid #f5a62344}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;padding:24px 30px}
.card{background:#111827;border-radius:12px;padding:20px;border:1px solid #1f2937}
.card .label{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}
.card .value{font-size:26px;font-weight:700;color:#fff}
.green{color:#00d4aa !important}.red{color:#ef4444 !important}.yellow{color:#f5a623 !important}
.section{padding:0 30px 24px}
.section h2{font-size:16px;color:#9ca3af;margin-bottom:16px;text-transform:uppercase;letter-spacing:1px;display:flex;justify-content:space-between;align-items:center}
.table{width:100%;border-collapse:collapse;background:#111827;border-radius:12px;overflow:hidden;border:1px solid #1f2937}
.table th{background:#1f2937;padding:12px 16px;text-align:left;font-size:12px;color:#6b7280;text-transform:uppercase}
.table td{padding:12px 16px;border-top:1px solid #1f2937;font-size:13px}
.pill{padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
.pill.buy{background:#00d4aa22;color:#00d4aa}
.pill.sell{background:#ef444422;color:#ef4444}
.pares-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.par-card{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:12px;text-align:center}
.par-nombre{font-size:11px;color:#9ca3af;margin-bottom:4px}
.par-precio{font-size:15px;font-weight:700;color:#fff}
.par-cambio{font-size:11px;margin-top:3px}
.pos{color:#00d4aa}.neg{color:#ef4444}
.btn{padding:8px 18px;border-radius:8px;border:none;cursor:pointer;font-size:13px;font-weight:600;transition:all 0.2s}
.btn-green{background:#00d4aa22;color:#00d4aa;border:1px solid #00d4aa44}
.btn-green:hover{background:#00d4aa44}
.btn-yellow{background:#f5a62322;color:#f5a623;border:1px solid #f5a62344}
.btn-yellow:hover{background:#f5a62344}
.btn-red{background:#ef444422;color:#ef4444;border:1px solid #ef444444}
.btn-red:hover{background:#ef444444}
.btns{display:flex;gap:10px;margin-bottom:20px;padding:0 30px}
.chart-container{background:#111827;border-radius:12px;border:1px solid #1f2937;padding:20px;margin:0 30px 24px;height:200px;position:relative}
.chart-line{fill:none;stroke:#00d4aa;stroke-width:2}
.chart-area{fill:url(#grad)}
.footer{text-align:center;padding:16px;color:#374151;font-size:12px}
.toast{position:fixed;top:20px;right:20px;background:#1f2937;color:#fff;padding:12px 20px;border-radius:10px;border:1px solid #374151;font-size:13px;display:none;z-index:999}
</style>
</head>
<body>
<div class="header">
  <h1>OKX Trading Bot</h1>
  <div style="display:flex;gap:10px;align-items:center">
    <span class="badge">REAL</span>
    <span style="color:#6b7280;font-size:13px" id="hora"></span>
  </div>
</div>

<div class="grid">
  <div class="card"><div class="label">Balance USDT</div><div class="value green" id="balance">$0.00</div></div>
  <div class="card"><div class="label">PnL Hoy</div><div class="value" id="pnl-hoy">+$0.00</div></div>
  <div class="card"><div class="label">PnL Total</div><div class="value" id="pnl-total">+$0.00</div></div>
  <div class="card"><div class="label">Trades Hoy</div><div class="value yellow" id="trades-hoy">0</div></div>
  <div class="card"><div class="label">Winrate</div><div class="value" id="winrate">0%</div></div>
  <div class="card"><div class="label">Estado Bot</div><div class="value" id="estado">INACTIVO</div></div>
  <div class="card"><div class="label">Posiciones</div><div class="value yellow" id="posiciones">0</div></div>
  <div class="card"><div class="label">Capital Inicial</div><div class="value">$""" + str(CAPITAL_TOTAL_USD) + """</div></div>
</div>

<div class="btns">
  <button class="btn btn-green" onclick="accion('iniciar')">▶ Iniciar Bot</button>
  <button class="btn btn-yellow" onclick="accion('pausar')">⏸ Pausar</button>
  <button class="btn btn-red" onclick="accion('detener')">⏹ Detener</button>
</div>

<div class="section">
  <h2>Rendimiento del Capital</h2>
  <div class="chart-container">
    <svg id="chart" width="100%" height="100%" preserveAspectRatio="none">
      <defs>
        <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#00d4aa" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="#00d4aa" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <text x="50%" y="50%" text-anchor="middle" fill="#6b7280" font-size="13">Sin datos aun</text>
    </svg>
  </div>
</div>

<div class="section">
  <h2>Posiciones Abiertas</h2>
  <table class="table">
    <thead><tr>
      <th>Par</th><th>Lado</th><th>Entrada</th><th>Actual</th>
      <th>Tamano</th><th>PnL</th><th>Stop Loss</th><th>Take Profit</th>
      <th>Confianza</th><th>Abierta</th>
    </tr></thead>
    <tbody id="ops"><tr><td colspan="10" style="text-align:center;color:#6b7280;padding:20px">Sin posiciones abiertas</td></tr></tbody>
  </table>
</div>

<div class="section">
  <h2>Historial de Trades</h2>
  <table class="table">
    <thead><tr>
      <th>Par</th><th>Lado</th><th>Entrada</th><th>Salida</th>
      <th>PnL</th><th>Duracion</th><th>Razon</th><th>Fecha</th>
    </tr></thead>
    <tbody id="historial"><tr><td colspan="8" style="text-align:center;color:#6b7280;padding:20px">Sin trades aun</td></tr></tbody>
  </table>
</div>

<div class="section">
  <h2>Mercado en Tiempo Real</h2>
  <div class="pares-grid" id="precios"><div style="color:#6b7280">Cargando...</div></div>
</div>

<div class="footer">Actualizacion cada 15 segundos — OKX Trading Bot v1.0</div>
<div class="toast" id="toast"></div>

<script>
function mostrarToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 3000);
}

async function accion(cmd) {
  try {
    const r = await fetch('/api/accion/' + cmd, {method: 'POST'});
    const d = await r.json();
    mostrarToast(d.mensaje || cmd + ' ejecutado');
    setTimeout(actualizar, 1000);
  } catch(e) { mostrarToast('Error: ' + e); }
}

function dibujarGrafica(datos) {
  const svg = document.getElementById('chart');
  if (!datos || datos.length < 2) return;
  const w = svg.clientWidth || 800;
  const h = svg.clientHeight || 160;
  const pad = 10;
  const valores = datos.map(d => d.balance);
  const minV = Math.min(...valores);
  const maxV = Math.max(...valores);
  const rango = maxV - minV || 1;
  const puntos = valores.map((v, i) => {
    const x = pad + (i / (valores.length - 1)) * (w - pad * 2);
    const y = pad + (1 - (v - minV) / rango) * (h - pad * 2);
    return x + ',' + y;
  });
  const primero = puntos[0].split(',');
  const ultimo  = puntos[puntos.length - 1].split(',');
  svg.innerHTML = '<defs><linearGradient id="grad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#00d4aa" stop-opacity="0.3"/><stop offset="100%" stop-color="#00d4aa" stop-opacity="0"/></linearGradient></defs>' +
    '<polyline class="chart-line" points="' + puntos.join(' ') + '"/>' +
    '<polygon class="chart-area" points="' + primero[0] + ',' + h + ' ' + puntos.join(' ') + ' ' + ultimo[0] + ',' + h + '"/>';
}

async function actualizar() {
  try {
    const r = await fetch('/api/estado');
    if (!r.ok) return;
    const d = await r.json();

    document.getElementById('hora').textContent = 'Actualizado: ' + d.hora;
    document.getElementById('balance').textContent = '$' + d.balance.toFixed(2);
    document.getElementById('trades-hoy').textContent = d.trades_hoy;
    document.getElementById('posiciones').textContent = d.posiciones;

    const ph = d.pnl_hoy;
    const eph = document.getElementById('pnl-hoy');
    eph.textContent = (ph>=0?'+':'') + '$' + ph.toFixed(2);
    eph.className = 'value ' + (ph>=0?'green':'red');

    const pt = d.pnl_total;
    const ept = document.getElementById('pnl-total');
    ept.textContent = (pt>=0?'+':'') + '$' + pt.toFixed(2);
    ept.className = 'value ' + (pt>=0?'green':'red');

    const ewr = document.getElementById('winrate');
    ewr.textContent = d.winrate + '%';
    ewr.className = 'value ' + (d.winrate>=50?'green':'red');

    const ee = document.getElementById('estado');
    ee.textContent = d.activo ? 'ACTIVO' : 'INACTIVO';
    ee.className = 'value ' + (d.activo?'green':'red');

    // Grafica
    if (d.balance_historico && d.balance_historico.length > 1) {
      dibujarGrafica(d.balance_historico);
    }

    // Posiciones abiertas
    const tbody = document.getElementById('ops');
    if (!d.operaciones || d.operaciones.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:#6b7280;padding:20px">Sin posiciones abiertas</td></tr>';
    } else {
      tbody.innerHTML = d.operaciones.map(op => {
        const pnl = op.pnl_actual || 0;
        const pc = pnl>=0?'#00d4aa':'#ef4444';
        return '<tr><td><strong>' + op.par + '</strong></td><td><span class="pill ' + op.lado + '">' + op.lado.toUpperCase() + '</span></td><td>$' + op.precio_entrada.toFixed(4) + '</td><td>$' + (op.precio_actual||0).toFixed(4) + '</td><td>$' + op.tamano_usdt.toFixed(2) + '</td><td style="color:' + pc + '">' + (pnl>=0?'+':'') + '$' + pnl.toFixed(2) + '</td><td style="color:#ef4444">$' + op.stop_loss.toFixed(4) + '</td><td style="color:#00d4aa">$' + op.take_profit.toFixed(4) + '</td><td>' + (op.confianza||0) + '%</td><td>' + (op.abierta_en||'-') + '</td></tr>';
      }).join('');
    }

    // Historial
    const thist = document.getElementById('historial');
    if (!d.historial || d.historial.length === 0) {
      thist.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#6b7280;padding:20px">Sin trades aun</td></tr>';
    } else {
      thist.innerHTML = d.historial.map(t => {
        const pnl = t.pnl_usdt || 0;
        const pc = pnl>=0?'#00d4aa':'#ef4444';
        return '<tr><td><strong>' + t.par + '</strong></td><td><span class="pill ' + t.lado + '">' + t.lado.toUpperCase() + '</span></td><td>$' + (t.precio_entrada||0).toFixed(4) + '</td><td>$' + (t.precio_salida||0).toFixed(4) + '</td><td style="color:' + pc + '">' + (pnl>=0?'+':'') + '$' + pnl.toFixed(2) + '</td><td>' + (t.duracion_min||0) + 'm</td><td style="color:#6b7280;font-size:11px">' + (t.razon_salida||'-') + '</td><td>' + (t.cerrada_en||'-') + '</td></tr>';
      }).join('');
    }

    // Precios
    const pg = document.getElementById('precios');
    if (!d.precios || d.precios.length === 0) {
      pg.innerHTML = '<div style="color:#6b7280">Sin datos</div>';
    } else {
      pg.innerHTML = d.precios.map(p =>
        '<div class="par-card"><div class="par-nombre">' + p.par + '</div><div class="par-precio">$' + Number(p.precio).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:4}) + '</div><div class="par-cambio ' + (p.cambio>=0?'pos':'neg') + '">' + (p.cambio>=0?'▲':'▼') + ' ' + Math.abs(p.cambio).toFixed(2) + '%</div></div>'
      ).join('');
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
                            precios.append({
                                "par":    par,
                                "precio": float(precio),
                                "cambio": float(cambio),
                            })
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

                if cmd == "iniciar" and motor:
                    if not motor.activo:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        t = threading.Thread(
                            target=lambda: loop.run_until_complete(motor.iniciar()),
                            daemon=True
                        )
                        t.start()
                        msg = "Bot iniciado"
                    else:
                        msg = "Bot ya estaba activo"
                elif cmd == "pausar" and motor:
                    motor.detener()
                    msg = "Bot pausado"
                elif cmd == "detener" and motor:
                    motor.detener()
                    msg = "Bot detenido"

                resp = json.dumps({"ok": True, "mensaje": msg}).encode()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', len(resp))
                self.end_headers()
                self.wfile.write(resp)
        except Exception:
            pass

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

                balance   = 0.0
                pnl_hoy   = 0.0
                pnl_total = 0.0
                trades    = 0
                activo    = False
                ops       = []
                ganados   = 0
                perdidos  = 0
                db        = None

                try:
                    if okx:
                        balance = okx.get_balance()
                    if motor:
                        pnl_hoy   = motor.pnl_hoy
                        pnl_total = motor.pnl_total
                        trades    = motor.trades_hoy
                        activo    = motor.activo
                        ops       = motor.operaciones
                        ganados   = motor.trades_ganados
                        perdidos  = motor.trades_perdidos
                        db        = motor.db
                except Exception:
                    pass

                winrate = 0
                if (ganados + perdidos) > 0:
                    winrate = int((ganados / (ganados + perdidos)) * 100)

                ops_data = []
                for op in ops:
                    try:
                        precio_actual = okx.get_price(op["par"]) if okx else 0.0
                        ops_data.append({
                            "par":            op["par"],
                            "lado":           op["lado"],
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
                balance_historico = []
                if db:
                    try:
                        trades_hist = db.get_trades_historial(20)
                        for t in trades_hist:
                            historial.append({
                                "par":           t.par,
                                "lado":          t.lado,
                                "precio_entrada": float(t.precio_entrada or 0),
                                "precio_salida":  float(t.precio_salida or 0),
                                "pnl_usdt":       float(t.pnl_usdt or 0),
                                "duracion_min":   int(t.duracion_min or 0),
                                "razon_salida":   t.razon_salida or "-",
                                "cerrada_en":     t.cerrada_en.strftime("%d/%m %H:%M") if t.cerrada_en else "-",
                            })
                        bal_hist = db.get_balance_historico(30)
                        for b in bal_hist:
                            balance_historico.append({
                                "fecha":   b.fecha.strftime("%d/%m"),
                                "balance": float(b.balance),
                            })
                    except Exception:
                        pass

                data = {
                    "activo":            activo,
                    "balance":           float(balance),
                    "pnl_hoy":           float(pnl_hoy),
                    "pnl_total":         float(pnl_total),
                    "trades_hoy":        int(trades),
                    "winrate":           int(winrate),
                    "posiciones":        len(ops_data),
                    "operaciones":       ops_data,
                    "historial":         historial,
                    "balance_historico": balance_historico,
                    "precios":           estado_panel["precios"],
                    "hora":              datetime.now().strftime("%H:%M:%S"),
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

    hilo_precios = threading.Thread(target=actualizar_precios_cache, daemon=True)
    hilo_precios.start()

    servidor = HTTPServer(('0.0.0.0', puerto), PanelHandler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    print(f"[OK] Panel web iniciado en http://localhost:{puerto}")
    return servidor