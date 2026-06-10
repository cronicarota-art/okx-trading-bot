import asyncio
from datetime import datetime

import sys
sys.path.insert(0, '.')
from config.settings import (
    TRADING_PAIRS, CAPITAL_TOTAL_USD, MAX_RISK_PER_TRADE,
    MAX_OPEN_TRADES, MAX_DAILY_LOSS, STOP_LOSS_PCT,
    TAKE_PROFIT_PCT, MIN_ORDER_USDT, TRAILING_PCT
)
from utils.indicators import Indicators
from utils.database import Database


class Motor:

    def __init__(self, okx, notifier):
        self.okx             = okx
        self.notifier        = notifier
        self.activo          = False
        self.operaciones     = []
        self.pnl_hoy         = 0.0
        self.pnl_total       = 0.0
        self.trades_hoy      = 0
        self.trades_ganados  = 0
        self.trades_perdidos = 0
        self.ciclo_num       = 0
        self.db              = Database()
        print("[INFO] Motor profesional iniciado")

    # ── CICLO PRINCIPAL ──────────────────────────────────

    async def iniciar(self):
        self.activo = True
        balance     = self.okx.get_total_balance_usdt()
        print(f"[OK] Motor activo | Balance total: ${balance:.2f} USDT")
        await self.notifier.enviar(
            f"*Motor de trading activo*\n\n"
            f"Balance total: ${balance:.2f} USDT\n"
            f"Pares: {len(TRADING_PAIRS)}\n"
            f"Riesgo por trade: {MAX_RISK_PER_TRADE*100:.0f}%\n"
            f"Stop Loss: {STOP_LOSS_PCT*100:.0f}% | Take Profit: {TAKE_PROFIT_PCT*100:.0f}%\n"
            f"Trailing Stop: {TRAILING_PCT*100:.1f}%\n"
            f"Revision cada 30 minutos"
        )
        while self.activo:
            try:
                await self.ciclo()
            except Exception as e:
                print(f"[ERROR] Ciclo: {e}")
                await self.notifier.enviar(f"*Error en ciclo*\n`{e}`")
            await asyncio.sleep(1800)

    async def ciclo(self):
        self.ciclo_num += 1
        ahora = datetime.now()
        print(f"\n{'='*50}")
        print(f"[CICLO #{self.ciclo_num}] {ahora.strftime('%d/%m/%Y %H:%M:%S')}")

        # 1. Monitorear posiciones abiertas
        await self.monitorear_posiciones()

        # 2. Buscar nuevas oportunidades
        if self.puede_abrir_trade():
            mejor = await self.encontrar_oportunidad()
            if mejor:
                await self.ejecutar_trade(mejor)

        # 3. Reporte cada hora (cada 2 ciclos)
        if self.ciclo_num % 2 == 0:
            await self.enviar_reporte()

        # 4. Reporte diario a las 9am
        if ahora.hour == 9 and ahora.minute < 30:
            await self.reporte_diario()

    # ── GESTIÓN DE RIESGO ────────────────────────────────

    def puede_abrir_trade(self):
        if not self.activo:
            return False
        if len(self.operaciones) >= MAX_OPEN_TRADES:
            print(f"[INFO] Max trades abiertos: {len(self.operaciones)}/{MAX_OPEN_TRADES}")
            return False
        balance_usdt = self.okx.get_balance("USDT")
        if balance_usdt < MIN_ORDER_USDT:
            print(f"[INFO] USDT insuficiente: ${balance_usdt:.2f}")
            return False
        total = self.okx.get_total_balance_usdt()
        perdida_pct = abs(self.pnl_hoy) / max(total, 1)
        if self.pnl_hoy < 0 and perdida_pct > MAX_DAILY_LOSS:
            print(f"[WARNING] Limite perdida diaria ({perdida_pct*100:.1f}%). Bot pausado.")
            self.activo = False
            asyncio.create_task(self.notifier.enviar(
                f"*Bot pausado*\n\nPerdida diaria maxima alcanzada: {perdida_pct*100:.1f}%\n"
                f"Usa /iniciar manana para reactivar."
            ))
            return False
        return True

    def calcular_tamano_orden(self):
        """Calcula el tamaño óptimo de la orden basado en el balance disponible."""
        balance_usdt = self.okx.get_balance("USDT")
        cantidad     = balance_usdt * MAX_RISK_PER_TRADE
        # Asegurar mínimo
        if cantidad < MIN_ORDER_USDT:
            if balance_usdt >= MIN_ORDER_USDT:
                cantidad = MIN_ORDER_USDT
            else:
                return 0
        # No más del 90% del balance disponible
        cantidad = min(cantidad, balance_usdt * 0.90)
        return round(cantidad, 2)

    # ── ANÁLISIS DE MERCADO ──────────────────────────────

    async def encontrar_oportunidad(self):
        print(f"[SCAN] Analizando {len(TRADING_PAIRS)} pares...")
        candidatos = []

        for par in TRADING_PAIRS:
            # Saltar pares ya abiertos
            if par in [op["par"] for op in self.operaciones]:
                continue
            try:
                resultado = self.analizar_par(par)
                if resultado:
                    candidatos.append(resultado)
                    print(f"[SIGNAL] {par}: {resultado['lado'].upper()} | "
                          f"F={resultado['fuerza']} | RSI={resultado['rsi']:.1f} | "
                          f"Confianza={resultado['confianza']}%")
                else:
                    pass  # Skip silencioso
            except Exception as e:
                print(f"[WARNING] Error {par}: {e}")

        if not candidatos:
            print("[INFO] Sin oportunidades en este ciclo")
            return None

        # Ordenar por fuerza
        candidatos.sort(key=lambda x: x["fuerza"], reverse=True)
        mejor = candidatos[0]
        print(f"[OK] Mejor oportunidad: {mejor['par']} | {mejor['lado'].upper()} | {mejor['confianza']}%")
        return mejor

    def analizar_par(self, par):
        """
        Analiza un par en 3 timeframes y retorna señal si cumple criterios.
        Solo opera en tendencias ALCISTAS o LATERALES para compras.
        Solo opera en tendencias BAJISTAS o LATERALES para ventas.
        """
        # Obtener velas
        velas_15m = self.okx.get_candles(par, "15m", 100)
        velas_1h  = self.okx.get_candles(par, "1H",  100)
        velas_4h  = self.okx.get_candles(par, "4H",  60)

        if len(velas_15m) < 50 or len(velas_1h) < 50 or len(velas_4h) < 50:
            return None

        a15m = Indicators.analisis_completo(velas_15m)
        a1h  = Indicators.analisis_completo(velas_1h)
        a4h  = Indicators.analisis_completo(velas_4h)

        if not a15m or not a1h or not a4h:
            return None

        señal_15m  = a15m["señal"]
        señal_1h   = a1h["señal"]
        señal_4h   = a4h["señal"]
        tendencia  = a4h["tendencia"]
        rsi_1h     = a1h["rsi"]
        rsi_4h     = a4h["rsi"]
        fuerza     = a15m["fuerza"] + a1h["fuerza"] + a4h["fuerza"]

        compras = sum(1 for s in [señal_15m, señal_1h, señal_4h]
                      if s in ["COMPRA", "COMPRA_FUERTE"])
        ventas  = sum(1 for s in [señal_15m, señal_1h, señal_4h]
                      if s in ["VENTA", "VENTA_FUERTE"])

        # COMPRA: mínimo 2 timeframes alcistas + tendencia no bajista + RSI no sobrecomprado
        if (compras >= 2
                and tendencia in ["ALCISTA", "LATERAL"]
                and rsi_1h < 65
                and rsi_4h < 70
                and fuerza >= 3):
            confianza = min(99, int((fuerza / 15) * 100) + (compras * 10))
            return {
                "par":       par,
                "lado":      "buy",
                "fuerza":    fuerza,
                "confianza": confianza,
                "rsi":       rsi_1h,
                "tendencia": tendencia,
                "razones":   a1h["razones"][:3],
                "analisis":  a1h,
            }

        # VENTA: mínimo 2 timeframes bajistas + tendencia no alcista + RSI no sobrevendido
        if (ventas >= 2
                and tendencia in ["BAJISTA", "LATERAL"]
                and rsi_1h > 55
                and rsi_4h > 50
                and fuerza <= -3):
            confianza = min(99, int((abs(fuerza) / 15) * 100) + (ventas * 10))
            return {
                "par":       par,
                "lado":      "sell",
                "fuerza":    fuerza,
                "confianza": confianza,
                "rsi":       rsi_1h,
                "tendencia": tendencia,
                "razones":   a1h["razones"][:3],
                "analisis":  a1h,
            }

        return None

    # ── EJECUCIÓN DE TRADES ──────────────────────────────

    async def ejecutar_trade(self, oportunidad):
        par       = oportunidad["par"]
        lado      = oportunidad["lado"]
        confianza = oportunidad["confianza"]
        razones   = oportunidad["razones"]
        rsi       = oportunidad["rsi"]
        tendencia = oportunidad["tendencia"]

        # Calcular tamaño
        tamano = self.calcular_tamano_orden()
        if tamano == 0:
            print(f"[SKIP] Balance insuficiente para operar")
            return

        precio = self.okx.get_price(par)
        if precio == 0:
            return

        # Stop loss y take profit
        if lado == "buy":
            stop_loss   = precio * (1 - STOP_LOSS_PCT)
            take_profit = precio * (1 + TAKE_PROFIT_PCT)
        else:
            stop_loss   = precio * (1 + STOP_LOSS_PCT)
            take_profit = precio * (1 - TAKE_PROFIT_PCT)

        razon_str = " | ".join(razones)

        print(f"[TRADE] {lado.upper()} {par} | ${tamano:.2f} | Confianza: {confianza}%")

        resultado = self.okx.place_market_order(par, lado, tamano)

        if resultado["ok"]:
            precio_real = resultado.get("precio_ref", precio)
            valor_real  = resultado.get("valor_usdt", tamano)

            op = {
                "orden_id":       resultado["orden_id"],
                "par":            par,
                "lado":           lado,
                "precio_entrada": precio_real,
                "tamaño_usdt":    valor_real,
                "stop_loss":      stop_loss,
                "take_profit":    take_profit,
                "trailing_max":   precio_real,
                "pnl_actual":     0.0,
                "abierta_en":     datetime.now(),
                "razon":          razon_str,
                "confianza":      confianza,
                "rsi":            rsi,
                "tendencia":      tendencia,
            }
            self.operaciones.append(op)
            self.trades_hoy += 1
            self.db.guardar_trade_abierto(op)

            await self.notifier.enviar(
                f"{'🟢 COMPRA' if lado == 'buy' else '🔴 VENTA'} ejecutada\n\n"
                f"Par: *{par}*\n"
                f"Precio entrada: `${precio_real:,.4f}`\n"
                f"Tamaño: `${valor_real:.2f} USDT`\n"
                f"Stop Loss: `${stop_loss:,.4f}` ({STOP_LOSS_PCT*100:.0f}%)\n"
                f"Take Profit: `${take_profit:,.4f}` ({TAKE_PROFIT_PCT*100:.0f}%)\n"
                f"Confianza: {confianza}%\n"
                f"RSI: {rsi:.1f} | Tendencia: {tendencia}\n"
                f"Razon: _{razon_str}_\n"
                f"🕐 {datetime.now().strftime('%H:%M:%S')}"
            )
        else:
            error = resultado.get("error", "Error desconocido")
            print(f"[ERROR] Trade fallido: {error}")
            await self.notifier.enviar(f"*Error en trade {par}*\n`{error}`")

    # ── MONITOREO DE POSICIONES ──────────────────────────

    async def monitorear_posiciones(self):
        if not self.operaciones:
            return

        balance_total = self.okx.get_total_balance_usdt()
        print(f"[MONITOR] {len(self.operaciones)} posicion(es) | Balance total: ${balance_total:.2f}")

        for op in self.operaciones[:]:
            par            = op["par"]
            precio_actual  = self.okx.get_price(par)
            precio_entrada = op["precio_entrada"]
            lado           = op["lado"]

            if precio_actual == 0:
                continue

            # Calcular PnL
            if lado == "buy":
                pnl_pct  = (precio_actual - precio_entrada) / precio_entrada
                cambio   = ((precio_actual - precio_entrada) / precio_entrada) * 100
            else:
                pnl_pct  = (precio_entrada - precio_actual) / precio_entrada
                cambio   = ((precio_entrada - precio_actual) / precio_entrada) * 100

            pnl_usdt         = pnl_pct * op["tamaño_usdt"]
            op["pnl_actual"] = pnl_usdt

            print(f"  {par}: ${precio_actual:,.4f} | PnL: {'+'if pnl_usdt>=0 else ''}{pnl_usdt:.2f} USDT ({cambio:+.2f}%)")

            # Trailing stop
            if lado == "buy" and precio_actual > op["trailing_max"]:
                op["trailing_max"] = precio_actual
                nuevo_sl = precio_actual * (1 - TRAILING_PCT)
                if nuevo_sl > op["stop_loss"]:
                    op["stop_loss"] = nuevo_sl
                    print(f"  [TRAIL] {par}: SL subido a ${nuevo_sl:,.4f}")
            elif lado == "sell" and precio_actual < op["trailing_max"]:
                op["trailing_max"] = precio_actual
                nuevo_sl = precio_actual * (1 + TRAILING_PCT)
                if nuevo_sl < op["stop_loss"]:
                    op["stop_loss"] = nuevo_sl
                    print(f"  [TRAIL] {par}: SL bajado a ${nuevo_sl:,.4f}")

            # Verificar cierre
            cerrar = False
            razon  = ""

            if lado == "buy":
                if precio_actual <= op["stop_loss"]:
                    cerrar = True
                    razon  = f"Stop Loss ({STOP_LOSS_PCT*100:.0f}%)"
                elif precio_actual >= op["take_profit"]:
                    cerrar = True
                    razon  = f"Take Profit ({TAKE_PROFIT_PCT*100:.0f}%)"
            else:
                if precio_actual >= op["stop_loss"]:
                    cerrar = True
                    razon  = f"Stop Loss ({STOP_LOSS_PCT*100:.0f}%)"
                elif precio_actual <= op["take_profit"]:
                    cerrar = True
                    razon  = f"Take Profit ({TAKE_PROFIT_PCT*100:.0f}%)"

            if cerrar:
                await self._cerrar_trade(op, precio_actual, pnl_usdt, razon)

    async def _cerrar_trade(self, op, precio_actual, pnl_usdt, razon):
        par  = op["par"]
        lado = op["lado"]
        lado_cierre = "sell" if lado == "buy" else "buy"

        print(f"[CLOSE] {par}: {razon} | PnL: {pnl_usdt:+.2f} USDT")

        resultado = self.okx.place_market_order(par, lado_cierre, op["tamaño_usdt"])

        if resultado["ok"]:
            self.pnl_hoy   += pnl_usdt
            self.pnl_total += pnl_usdt

            if pnl_usdt >= 0:
                self.trades_ganados  += 1
                emoji = "💰 GANANCIA"
            else:
                self.trades_perdidos += 1
                emoji = "📉 PERDIDA"

            duracion = int((datetime.now() - op["abierta_en"]).total_seconds() / 60)
            pct      = (pnl_usdt / op["tamaño_usdt"]) * 100

            self.db.cerrar_trade(op["orden_id"], precio_actual, pnl_usdt, razon)
            self.operaciones.remove(op)

            await self.notifier.enviar(
                f"{emoji}\n\n"
                f"Par: *{par}*\n"
                f"Entrada: `${op['precio_entrada']:,.4f}`\n"
                f"Salida: `${precio_actual:,.4f}`\n"
                f"PnL: `{'+'if pnl_usdt>=0 else ''}{pnl_usdt:.2f} USDT ({pct:+.2f}%)`\n"
                f"Duracion: {duracion} min\n"
                f"Razon: _{razon}_\n"
                f"PnL total hoy: `{'+'if self.pnl_hoy>=0 else ''}{self.pnl_hoy:.2f} USDT`"
            )

    # ── REPORTES ─────────────────────────────────────────

    async def enviar_reporte(self):
        balance_usdt  = self.okx.get_balance("USDT")
        balance_total = self.okx.get_total_balance_usdt()
        posiciones    = self.okx.get_posiciones_abiertas()

        winrate = 0
        total_trades = self.trades_ganados + self.trades_perdidos
        if total_trades > 0:
            winrate = int((self.trades_ganados / total_trades) * 100)

        pnl_emoji = "📈" if self.pnl_hoy >= 0 else "📉"

        lineas = [
            f"📊 *Reporte | {datetime.now().strftime('%d/%m/%Y %H:%M')}*\n",
            f"💵 USDT libre: `${balance_usdt:,.2f}`",
            f"💰 Valor total: `${balance_total:,.2f} USDT`",
            f"{pnl_emoji} PnL hoy: `{'+'if self.pnl_hoy>=0 else ''}{self.pnl_hoy:.2f} USDT`",
            f"📈 PnL total: `{'+'if self.pnl_total>=0 else ''}{self.pnl_total:.2f} USDT`",
            f"🔄 Trades hoy: {self.trades_hoy} | Winrate: {winrate}%",
        ]

        if posiciones:
            lineas.append(f"\n*Posiciones abiertas:*")
            for p in posiciones:
                lineas.append(f"• {p['ccy']}: {p['cantidad']:.4f} = `${p['valor_usdt']:.2f}`")

        if self.operaciones:
            lineas.append(f"\n*Trades del bot:*")
            for op in self.operaciones:
                pnl = op.get("pnl_actual", 0)
                lineas.append(
                    f"• {op['par']} {op['lado'].upper()} | "
                    f"PnL: `{'+'if pnl>=0 else ''}{pnl:.2f}`"
                )

        await self.notifier.enviar("\n".join(lineas))

    async def reporte_diario(self):
        balance_total = self.okx.get_total_balance_usdt()
        stats         = self.db.get_estadisticas()
        pnl_emoji     = "📈" if self.pnl_hoy >= 0 else "📉"

        self.db.guardar_balance_diario(
            balance    = balance_total,
            pnl_dia    = self.pnl_hoy,
            trades_dia = self.trades_hoy,
            ganados    = self.trades_ganados,
            perdidos   = self.trades_perdidos,
        )

        await self.notifier.enviar(
            f"🌅 *Reporte Diario — {datetime.now().strftime('%d/%m/%Y')}*\n\n"
            f"💰 Balance total: `${balance_total:,.2f} USDT`\n"
            f"{pnl_emoji} PnL hoy: `{'+'if self.pnl_hoy>=0 else ''}{self.pnl_hoy:.2f} USDT`\n"
            f"📈 PnL total acumulado: `{'+'if self.pnl_total>=0 else ''}{self.pnl_total:.2f} USDT`\n\n"
            f"🔄 Trades hoy: {self.trades_hoy}\n"
            f"✅ Ganados: {self.trades_ganados}\n"
            f"❌ Perdidos: {self.trades_perdidos}\n"
            f"🎯 Winrate total: {stats.get('winrate', 0)}%\n\n"
            f"🏆 Mejor trade: `+${stats.get('mejor_trade', 0):.2f}`\n"
            f"📉 Peor trade: `${stats.get('peor_trade', 0):.2f}`\n"
            f"📊 Total trades historico: {stats.get('total_trades', 0)}"
        )

        # Reset contadores diarios
        self.pnl_hoy         = 0.0
        self.trades_hoy      = 0
        self.trades_ganados  = 0
        self.trades_perdidos = 0

    def detener(self):
        self.activo = False
        print("[INFO] Motor detenido")