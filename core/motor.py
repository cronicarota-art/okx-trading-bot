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

    async def iniciar(self):
        self.activo = True
        balance     = self.okx.get_total_balance_usdt()
        print(f"[OK] Motor activo | Balance total: ${balance:.2f} USDT")
        await self.notifier.enviar(
            f"*Motor de trading activo*\n\n"
            f"Balance total: ${balance:.2f} USDT\n"
            f"Pares: {len(TRADING_PAIRS)}\n"
            f"Riesgo por trade: {MAX_RISK_PER_TRADE*100:.0f}%\n"
            f"Stop Loss: {STOP_LOSS_PCT*100:.1f}% | Take Profit: {TAKE_PROFIT_PCT*100:.1f}%\n"
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

        await self.monitorear_posiciones()

        if self.puede_abrir_trade():
            mejor = await self.encontrar_oportunidad()
            if mejor:
                await self.ejecutar_trade(mejor)

        if self.ciclo_num % 2 == 0:
            await self.enviar_reporte()

        if ahora.hour == 9 and ahora.minute < 30:
            await self.reporte_diario()

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
        total       = self.okx.get_total_balance_usdt()
        perdida_pct = abs(self.pnl_hoy) / max(total, 1)
        if self.pnl_hoy < 0 and perdida_pct > MAX_DAILY_LOSS:
            print(f"[WARNING] Limite perdida diaria ({perdida_pct*100:.1f}%). Bot pausado.")
            self.activo = False
            asyncio.create_task(self.notifier.enviar(
                f"*Bot pausado*\nPerdida diaria maxima: {perdida_pct*100:.1f}%\n"
                f"Usa /iniciar manana para reactivar."
            ))
            return False
        return True

    def calcular_tamano_orden(self):
        balance_usdt = self.okx.get_balance("USDT")
        cantidad     = balance_usdt * MAX_RISK_PER_TRADE
        if cantidad < MIN_ORDER_USDT:
            if balance_usdt >= MIN_ORDER_USDT:
                cantidad = MIN_ORDER_USDT
            else:
                return 0
        cantidad = min(cantidad, balance_usdt * 0.90)
        return round(cantidad, 2)

    async def encontrar_oportunidad(self):
        print(f"[SCAN] Analizando {len(TRADING_PAIRS)} pares...")
        candidatos = []

        for par in TRADING_PAIRS:
            if par in [op["par"] for op in self.operaciones]:
                print(f"[SKIP] {par}: ya hay posicion abierta")
                continue
            try:
                resultado = self.analizar_par(par)
                if resultado:
                    candidatos.append(resultado)
                    print(f"[SIGNAL] {par}: {resultado['lado'].upper()} | "
                          f"F={resultado['fuerza']} | RSI={resultado['rsi']:.1f} | "
                          f"Confianza={resultado['confianza']}%")
                else:
                    print(f"[SKIP] {par}: sin señal suficiente")
            except Exception as e:
                print(f"[WARNING] Error {par}: {e}")

        if not candidatos:
            print("[INFO] Sin oportunidades en este ciclo")
            return None

        candidatos.sort(key=lambda x: x["fuerza"], reverse=True)
        mejor = candidatos[0]
        print(f"[OK] Mejor: {mejor['par']} | {mejor['lado'].upper()} | {mejor['confianza']}%")
        return mejor

    def analizar_par(self, par):
        velas_15m = self.okx.get_candles(par, "15m", 100)
        velas_1h  = self.okx.get_candles(par, "1H",  100)
        velas_4h  = self.okx.get_candles(par, "4H",  60)

        if len(velas_15m) < 50 or len(velas_1h) < 50 or len(velas_4h) < 50:
            print(f"  {par}: velas insuficientes")
            return None

        a15m = Indicators.analisis_completo(velas_15m)
        a1h  = Indicators.analisis_completo(velas_1h)
        a4h  = Indicators.analisis_completo(velas_4h)

        if not a15m or not a1h or not a4h:
            return None

        señal_15m = a15m["señal"]
        señal_1h  = a1h["señal"]
        señal_4h  = a4h["señal"]
        tendencia = a4h["tendencia"]
        rsi_1h    = a1h["rsi"]
        rsi_4h    = a4h["rsi"]
        fuerza    = a15m["fuerza"] + a1h["fuerza"] + a4h["fuerza"]

        print(f"  {par}: {señal_15m}/{señal_1h}/{señal_4h} | "
              f"F={fuerza} | RSI={rsi_1h:.1f}/{rsi_4h:.1f} | Tend={tendencia}")

        compras = sum(1 for s in [señal_15m, señal_1h, señal_4h]
                      if s in ["COMPRA", "COMPRA_FUERTE"])
        ventas  = sum(1 for s in [señal_15m, señal_1h, señal_4h]
                      if s in ["VENTA", "VENTA_FUERTE"])

        # COMPRA: 2+ timeframes alcistas, tendencia no bajista, RSI no sobrecomprado
        if compras >= 2 and tendencia != "BAJISTA" and rsi_1h < 68 and fuerza >= 2:
            confianza = min(99, 30 + int((fuerza / 12) * 50) + compras * 10)
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

        # VENTA: 2+ timeframes bajistas, tendencia no alcista, RSI no sobrevendido
        if ventas >= 2 and tendencia != "ALCISTA" and rsi_1h > 52 and fuerza <= -2:
            confianza = min(99, 30 + int((abs(fuerza) / 12) * 50) + ventas * 10)
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

    async def ejecutar_trade(self, oportunidad):
        par       = oportunidad["par"]
        lado      = oportunidad["lado"]
        confianza = oportunidad["confianza"]
        razones   = oportunidad["razones"]
        rsi       = oportunidad["rsi"]
        tendencia = oportunidad["tendencia"]

        tamano = self.calcular_tamano_orden()
        if tamano == 0:
            print(f"[SKIP] Balance insuficiente para operar")
            return

        precio = self.okx.get_price(par)
        if precio == 0:
            return

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
                f"Stop Loss: `${stop_loss:,.4f}` ({STOP_LOSS_PCT*100:.1f}%)\n"
                f"Take Profit: `${take_profit:,.4f}` ({TAKE_PROFIT_PCT*100:.1f}%)\n"
                f"Confianza: {confianza}%\n"
                f"RSI: {rsi:.1f} | Tendencia: {tendencia}\n"
                f"Razon: _{razon_str}_\n"
                f"🕐 {datetime.now().strftime('%H:%M:%S')}"
            )
        else:
            error = resultado.get("error", "Error desconocido")
            print(f"[ERROR] Trade fallido: {error}")
            await self.notifier.enviar(f"*Error en trade {par}*\n`{error}`")

    async def monitorear_posiciones(self):
        if not self.operaciones:
            return

        balance_total = self.okx.get_total_balance_usdt()
        print(f"[MONITOR] {len(self.operaciones)} posicion(es) | Total: ${balance_total:.2f}")

        for op in self.operaciones[:]:
            par            = op["par"]
            precio_actual  = self.okx.get_price(par)
            precio_entrada = op["precio_entrada"]
            lado           = op["lado"]

            if precio_actual == 0:
                continue

            if lado == "buy":
                pnl_pct = (precio_actual - precio_entrada) / precio_entrada
            else:
                pnl_pct = (precio_entrada - precio_actual) / precio_entrada

            pnl_usdt         = pnl_pct * op["tamaño_usdt"]
            op["pnl_actual"] = pnl_usdt
            cambio           = pnl_pct * 100

            print(f"  {par}: ${precio_actual:,.4f} | PnL: {pnl_usdt:+.2f} USDT ({cambio:+.2f}%)")

            # Trailing stop
            if lado == "buy" and precio_actual > op["trailing_max"]:
                op["trailing_max"] = precio_actual
                nuevo_sl = precio_actual * (1 - TRAILING_PCT)
                if nuevo_sl > op["stop_loss"]:
                    op["stop_loss"] = nuevo_sl
                    print(f"  [TRAIL] {par}: SL -> ${nuevo_sl:,.4f}")
            elif lado == "sell" and precio_actual < op["trailing_max"]:
                op["trailing_max"] = precio_actual
                nuevo_sl = precio_actual * (1 + TRAILING_PCT)
                if nuevo_sl < op["stop_loss"]:
                    op["stop_loss"] = nuevo_sl
                    print(f"  [TRAIL] {par}: SL -> ${nuevo_sl:,.4f}")

            cerrar = False
            razon  = ""
            if lado == "buy":
                if precio_actual <= op["stop_loss"]:
                    cerrar = True
                    razon  = f"Stop Loss ({STOP_LOSS_PCT*100:.1f}%)"
                elif precio_actual >= op["take_profit"]:
                    cerrar = True
                    razon  = f"Take Profit ({TAKE_PROFIT_PCT*100:.1f}%)"
            else:
                if precio_actual >= op["stop_loss"]:
                    cerrar = True
                    razon  = f"Stop Loss ({STOP_LOSS_PCT*100:.1f}%)"
                elif precio_actual <= op["take_profit"]:
                    cerrar = True
                    razon  = f"Take Profit ({TAKE_PROFIT_PCT*100:.1f}%)"

            if cerrar:
                await self._cerrar_trade(op, precio_actual, pnl_usdt, razon)

    async def _cerrar_trade(self, op, precio_actual, pnl_usdt, razon):
        par         = op["par"]
        lado        = op["lado"]
        lado_cierre = "sell" if lado == "buy" else "buy"

        print(f"[CLOSE] {par}: {razon} | PnL: {pnl_usdt:+.2f} USDT")
        resultado = self.okx.place_market_order(par, lado_cierre, op["tamaño_usdt"])

        if resultado["ok"]:
            self.pnl_hoy   += pnl_usdt
            self.pnl_total += pnl_usdt

            if pnl_usdt >= 0:
                self.trades_ganados += 1
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
                f"PnL: `{pnl_usdt:+.2f} USDT ({pct:+.2f}%)`\n"
                f"Duracion: {duracion} min\n"
                f"Razon: _{razon}_\n"
                f"PnL total hoy: `{self.pnl_hoy:+.2f} USDT`"
            )

    async def enviar_reporte(self):
        balance_usdt  = self.okx.get_balance("USDT")
        balance_total = self.okx.get_total_balance_usdt()
        posiciones    = self.okx.get_posiciones_abiertas()

        total_trades = self.trades_ganados + self.trades_perdidos
        winrate      = int((self.trades_ganados / total_trades) * 100) if total_trades > 0 else 0
        pnl_emoji    = "📈" if self.pnl_hoy >= 0 else "📉"

        lineas = [
            f"📊 *Reporte | {datetime.now().strftime('%d/%m/%Y %H:%M')}*\n",
            f"💵 USDT libre: `${balance_usdt:,.2f}`",
            f"💰 Valor total: `${balance_total:,.2f} USDT`",
            f"{pnl_emoji} PnL hoy: `{self.pnl_hoy:+.2f} USDT`",
            f"📈 PnL total: `{self.pnl_total:+.2f} USDT`",
            f"🔄 Trades hoy: {self.trades_hoy} | Winrate: {winrate}%",
        ]

        if posiciones:
            lineas.append(f"\n*Posiciones en OKX:*")
            for p in posiciones:
                lineas.append(f"• {p['ccy']}: {p['cantidad']:.4f} = `${p['valor_usdt']:.2f}`")

        if self.operaciones:
            lineas.append(f"\n*Trades activos del bot:*")
            for op in self.operaciones:
                pnl = op.get("pnl_actual", 0)
                lineas.append(
                    f"• {op['par']} {op['lado'].upper()} | "
                    f"Entrada: ${op['precio_entrada']:,.4f} | "
                    f"PnL: `{pnl:+.2f}`"
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
            f"{pnl_emoji} PnL hoy: `{self.pnl_hoy:+.2f} USDT`\n"
            f"📈 PnL acumulado: `{self.pnl_total:+.2f} USDT`\n\n"
            f"🔄 Trades hoy: {self.trades_hoy}\n"
            f"✅ Ganados: {self.trades_ganados}\n"
            f"❌ Perdidos: {self.trades_perdidos}\n"
            f"🎯 Winrate total: {stats.get('winrate', 0)}%\n\n"
            f"🏆 Mejor trade: `+${stats.get('mejor_trade', 0):.2f}`\n"
            f"📉 Peor trade: `${stats.get('peor_trade', 0):.2f}`\n"
            f"📊 Total historico: {stats.get('total_trades', 0)} trades"
        )

        self.pnl_hoy         = 0.0
        self.trades_hoy      = 0
        self.trades_ganados  = 0
        self.trades_perdidos = 0

    def detener(self):
        self.activo = False
        print("[INFO] Motor detenido")