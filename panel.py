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
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;padding:24px 30px}
.card{background:#111827;border-radius:12px;padding:20px;border:1px solid #1f2937}
.card .label{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}
.card .value{font-size:28px;font-weight:700;color:#fff}
.green{color:#00d4aa !important}
.red{color:#ef4444 !important}
.yellow{color:#f5a623 !important}
.section{padding:0 30px 24px}
.section h2{font-size:16px;color:#9ca3af;margin-bottom:16px;text-transform:uppercase;letter-spacing:1px}
.table{width:100%;border-collapse:collapse;background:#111827;border-radius:12px;overflow:hidden;border:1px solid #1f2937}
.table th{background:#1f2937;padding:12px 16px;text-align:left;font-size:12px;color:#6b7280;text-transform:uppercase}
.table td{padding:14px 16px;border-top:1px solid #1f2937;font-size:14px}
.pill{padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
.pill.buy{background:#00d4aa22;color:#00d4aa}
.pill.sell{background:#ef444422;color:#ef4444}
.pares-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.par-card{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:14px;text-align:center}
.par-nombre{font-size:12px;color:#9ca3af;margin-bottom:6px}
.par-precio{font-size:16px;font-weight:700;color:#fff}
.par-cambio{font-size:12px;margin-top:4px}
.pos{color:#00d4aa}
.neg{color:#ef4444}
.footer{text-align:center;padding:20px;color:#374151;font-size:12px}
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
<div class="section">
  <h2>Posiciones Abiertas</h2>
  <table class="table">
    <thead><tr>
      <th>Par</th><th>Lado</th><th>Entrada</th><th>Actual</th>
      <th>Tamano</th><th>PnL</th><th>Stop Loss</th><th>Take Profit</th>
      <th>Confianza</th><th>Abierta</th>
    </tr></thead>
    <tbody id="ops"><tr><td colspan="10" style="text-align:center;color:#6b7280;padding:30px">Sin posiciones abiertas</td></tr></tbody>
  </table>
</div>
<div class="section">
  <h2>Mercado en Tiempo Real</h2>
  <div class="pares-grid" id="precios"><div style="color:#6b7280">Cargando...</div></div>
</div>
<div class="footer">Actualizacion cada 15 segundos — OKX Trading Bot v1.0</div>
<script>
async function actualizar() {
  try {
    const resp = await fetch('/api/estado');
    if (!resp.ok) return;
    const d = await resp.json();
    document.getElementById('hora').textContent = 'Actualizado: ' + d.hora;
    document.getElementById('balance').textContent = '$' + d.balance.toFixed(2);
    document.getElementById('trades-hoy').textContent = d.trades_hoy;
    document.getElementById('posiciones').textContent = d.posiciones;
    const ph = d.pnl_hoy;
    const eph = document.getElementById('pnl-hoy');
    eph.textContent = (ph >= 0 ? '+' : '') + '$' + ph.toFixed(2);
    eph.className = 'value ' + (ph >= 0 ? 'green' : 'red');
    const pt = d.pnl_total;
    const ept = document.getElementById('pnl-total');
    ept.textContent = (pt >= 0 ? '+' : '') + '$' + pt.toFixed(2);
    ept.className = 'value ' + (pt >= 0 ? 'green' : 'red');
    const wr = d.winrate;
    const ewr = document.getElementById('winrate');
    ewr.textContent = wr + '%';
    ewr.className = 'value ' + (wr >= 50 ? 'green' : 'red');
    const ee = document.getElementById('estado');
    ee.textContent = d.activo ? 'ACTIVO' : 'INACTIVO';
    ee.className = 'value ' + (d.activo ? 'green' : 'red');
    const tbody = document.getElementById('ops');
    if (!d.operaciones || d.operaciones.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:#6b7280;padding:30px">Sin posiciones abiertas</td></tr>';
    } else {
      tbody.innerHTML = d.operaciones.map(op => {
        const pnl = op.pnl_actual || 0;
        const pc = pnl >= 0 ? '#00d4aa' : '#ef4444';
        return '<tr><td><strong>' + op.par + '</strong></td><td><span class="pill ' + op.lado + '">' + op.lado.toUpperCase() + '</span></td><td>$' + op.precio_entrada.toFixed(4) + '</td><td>$' + (op.precio_actual||0).toFixed(4) + '</td><td>$' + op.tamano_usdt.toFixed(2) + '</td><td style="color:' + pc + '">' + (pnl>=0?'+':'') + '$' + pnl.toFixed(2) + '</td><td style="color:#ef4444">$' + op.stop_loss.toFixed(4) + '</td><td style="color:#00d4aa">$' + op.take_profit.toFixed(4) + '</td><td>' + (op.confianza||0) + '%</td><td>' + (op.abierta_en||'-') + '</td></tr>';
      }).join('');
    }
    const pg = document.getElementById('precios');
    if (!d.precios || d.precios.length === 0) {
      pg.innerHTML = '<div style="color:#6b7280">Sin datos</div>';
    } else {
      pg.innerHTML = d.precios.map(p =>
        '<div class="par-card"><div class="par-nombre">' + p.par + '</div><div class="par-precio">$' + Number(p.precio).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:4}) + '</div><div class="par-cambio ' + (p.cambio >= 0 ? 'pos' : 'neg') + '">' + (p.cambio >= 0 ? '▲' : '▼') + ' ' + Math.abs(p.cambio).toFixed(2) + '%</div></div>'
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
    "motor":   None,
    "okx":     None,
    "precios": [],
}


def actualizar_precios_cache():
    """Actualiza los precios en segundo plano cada 30 segundos."""
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

                data = {
                    "activo":      activo,
                    "balance":     float(balance),
                    "pnl_hoy":     float(pnl_hoy),
                    "pnl_total":   float(pnl_total),
                    "trades_hoy":  int(trades),
                    "winrate":     int(winrate),
                    "posiciones":  len(ops_data),
                    "operaciones": ops_data,
                    "precios":     estado_panel["precios"],
                    "hora":        datetime.now().strftime("%H:%M:%S"),
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

    # Hilo para actualizar precios en segundo plano
    hilo_precios = threading.Thread(target=actualizar_precios_cache, daemon=True)
    hilo_precios.start()

    servidor = HTTPServer(('0.0.0.0', puerto), PanelHandler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    print(f"[OK] Panel web iniciado en http://localhost:{puerto}")
    return servidor