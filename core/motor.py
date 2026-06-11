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

PARES_PRINCIPALES = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]


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
        print("[INFO] Motor hibrido iniciado (Grid + Trend + RSI)")

    async def iniciar(self):
        self.activo = True
        balance     = self.okx.get_total_balance_usdt()
        print(f"[OK] Motor activo | Balance: ${balance:.2f} USDT")
        await self.notifier.enviar(
            f"*Motor de trading activo*\n\n"
            f"Balance: ${balance:.2f} USDT\n"
            f"Estrategia: Grid + Trend + RSI\n"
            f"Pares: BTC, ETH, SOL\n"
            f"Capital por par: ~${balance/3:.2f} USDT\n"
            f"Stop Loss: {STOP_LOSS_PCT*100:.1f}% | Take Profit: {TAKE_PROFIT_PCT*100:.1f}%\n"
            f"Trailing Stop: {TRAILING_PCT*100:.1f}%\n"
            f"Revision cada 15 minutos"
        )
        while self.activo:
            try:
                await self.ciclo()
            except Exception as e:
                print(f"[ERROR] Ciclo: {e}")
                await self.notifier.enviar(f"*Error en ciclo*\n`{e}`")
            await asyncio.sleep(900)

    async def ciclo(self):
        self.ciclo_num += 1
        ahora = datetime.now()
        print(f"\n{'='*50}")
        print(f"[CICLO #{self.ciclo_num}] {ahora.strftime('%d/%m/%Y %H:%M:%S')}")

        await self.monitorear_posiciones()

        if self.puede_abrir_trade():
            await self.escanear_y_operar()

        if self.ciclo_num % 4 == 0:
            await self.enviar_reporte()

        if ahora.hour == 9 and ahora.minute < 15:
            await self.reporte_diario()

    def puede_abrir_trade(self):
        if not self.activo:
            return False
        balance_usdt = self.okx.get_balance("USDT")
        if balance_usdt < MIN_ORDER_USDT:
            print(f"[INFO] USDT insuficiente: ${balance_usdt:.2f}")
            return False
        total        = self.okx.get_total_balance_usdt()
        perdida_pct  = abs(self.pnl_hoy) / max(total, 1)
        if self.pnl_hoy < 0 and perdida_pct > MAX_DAILY_LOSS:
            print(f"[WARNING] Limite perdida diaria ({perdida_pct*100:.1f}%)")
            self.activo = False
            asyncio.create_task(self.notifier.enviar(
                f"*Bot pausado — Perdida diaria maxima*\n"
                f"Perdida: {perdida_pct*100:.1f}%\n"
                f"Usa /iniciar manana."
            ))
            return False
        return True

    def calcular_tamano(self, par):
        balance_usdt = self.okx.get_balance("USDT")
        pares_libres = len([p for p in PARES_PRINCIPALES
                            if p not in [op["par"] for op in self.operaciones]])
        if pares_libres == 0:
            return 0
        por_par = balance_usdt / max(pares_libres, 1)
        tamano  = min(por_par * 0.90, balance_usdt * 0.90)
        if tamano < MIN_ORDER_USDT:
            if balance_usdt >= MIN_ORDER_USDT:
                tamano = MIN_ORDER_USDT
            else:
                return 0
        return round(tamano, 2)

    async def escanear_y_operar(self):
        print(f"[SCAN] Analizando BTC, ETH, SOL...")
        candidatos = []

        for par in PARES_PRINCIPALES:
            if par in [op["par"] for op in self.operaciones]:
                print(f"  {par}: posicion abierta")
                continue
            try:
                señal = self.analizar_par(par)
                if señal:
                    candidatos.append(señal)
                    print(f"  [SIGNAL] {par}: {señal['tipo']} | "
                          f"RSI={señal['rsi']:.0f} | Score={señal['score']:.0f}")
            except Exception as e:
                print(f"  [ERROR] {par}: {e}")

        if not candidatos:
            print("[INFO] Sin señales en este ciclo")
            return

        candidatos.sort(key=lambda x: x["score"], reverse=True)
        mejor = candidatos[0]
        tamano = self.calcular_tamano(mejor["par"])
        if tamano > 0:
            await self.ejecutar_compra(mejor, tamano)

    def analizar_par(self, par):
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

        rsi_15m   = a15m["rsi"]
        rsi_1h    = a1h["rsi"]
        rsi_4h    = a4h["rsi"]
        tendencia = a4h["tendencia"]
        boll_1h   = a1h["bollinger"]
        macd_1h   = a1h["macd"]
        señal_15m = a15m["señal"]
        señal_1h  = a1h["señal"]
        señal_4h  = a4h["señal"]

        compras_count = sum(1 for s in [señal_15m, señal_1h, señal_4h]
                            if s in ["COMPRA", "COMPRA_FUERTE"])

        print(f"  {par}: RSI={rsi_15m:.0f}/{rsi_1h:.0f}/{rsi_4h:.0f} | "
              f"{señal_15m}/{señal_1h}/{señal_4h} | {tendencia}")

        score = 0
        tipo  = ""
        razon = []

        # ESTRATEGIA 1: RSI sobreventa — mejor señal de rebote
        if rsi_1h < 28:
            score += 50
            tipo   = "RSI_SOBREVENTA_EXTREMA"
            razon.append(f"RSI 1H extremo: {rsi_1h:.0f}")
        elif rsi_1h < 35:
            score += 35
            tipo   = "RSI_SOBREVENTA"
            razon.append(f"RSI 1H sobreventa: {rsi_1h:.0f}")
        elif rsi_1h < 42:
            score += 20
            tipo   = "RSI_BAJO"
            razon.append(f"RSI 1H bajo: {rsi_1h:.0f}")

        if rsi_15m < 30:
            score += 20
            razon.append(f"RSI 15m sobreventa: {rsi_15m:.0f}")
        elif rsi_15m < 40:
            score += 10
            razon.append(f"RSI 15m bajo: {rsi_15m:.0f}")

        # ESTRATEGIA 2: Bollinger inferior
        if boll_1h["posicion"] == "SOBREVENTA":
            score += 30
            tipo   = tipo or "BOLLINGER_INFERIOR"
            razon.append("Precio en banda inferior Bollinger")
        elif boll_1h["posicion"] == "ZONA_BAJA":
            score += 15
            razon.append("Precio zona baja Bollinger")

        # ESTRATEGIA 3: MACD cruce alcista
        if macd_1h.get("cruce_alcista"):
            score += 25
            tipo   = tipo or "MACD_CRUCE"
            razon.append("MACD cruce alcista")
        elif macd_1h.get("macd", 0) > macd_1h.get("signal", 0):
            score += 8
            razon.append("MACD positivo")

        # ESTRATEGIA 4: Tendencia alcista con momentum
        if tendencia == "ALCISTA" and compras_count >= 2:
            score += 25
            tipo   = tipo or "TREND_FOLLOWING"
            razon.append("Tendencia alcista confirmada")
        elif tendencia == "LATERAL" and compras_count >= 2:
            score += 15
            razon.append("Tendencia lateral con compras")

        # ESTRATEGIA 5: Confirmacion multitimeframe
        if compras_count == 3:
            score += 25
            razon.append("3 timeframes alineados")
        elif compras_count == 2:
            score += 12
            razon.append("2 timeframes alineados")

        # FILTROS DE PROTECCION
        if rsi_1h > 70:
            score -= 40
        if rsi_4h > 72:
            score -= 25
        # Bajista sin sobreventa = riesgo alto
        if tendencia == "BAJISTA" and rsi_1h > 45:
            score -= 20
        # RSI muy alto en bajista = no operar
        if tendencia == "BAJISTA" and rsi_1h > 60:
            score -= 30

        # Score minimo para operar
        if score < 20 or not tipo:
            return None

        return {
            "par":       par,
            "tipo":      tipo,
            "score":     score,
            "rsi":       rsi_1h,
            "tendencia": tendencia,
            "razones":   razon[:3],
        }

    async def ejecutar_compra(self, señal, tamano):
        par     = señal["par"]
        tipo    = señal["tipo"]
        score   = señal["score"]
        razones = señal["razones"]
        rsi     = señal["rsi"]

        precio      = self.okx.get_price(par)
        stop_loss   = precio * (1 - STOP_LOSS_PCT)
        take_profit = precio * (1 + TAKE_PROFIT_PCT)
        razon_str   = " | ".join(razones)

        print(f"[TRADE] COMPRA {par} | ${tamano:.2f} | Score={score} | {tipo}")
        resultado = self.okx.place_market_order(par, "buy", tamano)

        if resultado["ok"]:
            precio_real = resultado.get("precio_ref", precio)
            valor_real  = resultado.get("valor_usdt", tamano)

            op = {
                "orden_id":       resultado["orden_id"],
                "par":            par,
                "lado":           "buy",
                "precio_entrada": precio_real,
                "tamaño_usdt":    valor_real,
                "stop_loss":      stop_loss,
                "take_profit":    take_profit,
                "trailing_max":   precio_real,
                "pnl_actual":     0.0,
                "abierta_en":     datetime.now(),
                "razon":          razon_str,
                "confianza":      min(99, score),
                "rsi":            rsi,
                "tendencia":      señal["tendencia"],
            }
            self.operaciones.append(op)
            self.trades_hoy += 1
            self.db.guardar_trade_abierto(op)

            await self.notifier.enviar(
                f"🟢 *COMPRA ejecutada*\n\n"
                f"Par: *{par}*\n"
                f"Estrategia: {tipo}\n"
                f"Precio: `${precio_real:,.4f}`\n"
                f"Tamaño: `${valor_real:.2f} USDT`\n"
                f"🛡 SL: `${stop_loss:,.4f}` (-{STOP_LOSS_PCT*100:.1f}%)\n"
                f"🎯 TP: `${take_profit:,.4f}` (+{TAKE_PROFIT_PCT*100:.1f}%)\n"
                f"📊 RSI: {rsi:.0f} | Score: {score}\n"
                f"📝 {razon_str}\n"
                f"🕐 {datetime.now().strftime('%H:%M:%S')}"
            )
        else:
            error = resultado.get("error", "Error desconocido")
            print(f"[ERROR] {par}: {error}")
            await self.notifier.enviar(f"*Error {par}*\n`{error}`")

    async def monitorear_posiciones(self):
        if not self.operaciones:
            return

        balance_total = self.okx.get_total_balance_usdt()
        print(f"[MONITOR] {len(self.operaciones)} posicion(es) | Total: ${balance_total:.2f}")

        for op in self.operaciones[:]:
            par            = op["par"]
            precio_actual  = self.okx.get_price(par)
            precio_entrada = op["precio_entrada"]

            if precio_actual == 0:
                continue

            pnl_pct          = (precio_actual - precio_entrada) / precio_entrada
            pnl_usdt         = pnl_pct * op["tamaño_usdt"]
            op["pnl_actual"] = pnl_usdt

            print(f"  {par}: ${precio_actual:,.4f} | "
                  f"PnL: {pnl_usdt:+.2f} USDT ({pnl_pct*100:+.2f}%)")

            if precio_actual > op["trailing_max"]:
                op["trailing_max"] = precio_actual
                nuevo_sl = precio_actual * (1 - TRAILING_PCT)
                if nuevo_sl > op["stop_loss"]:
                    op["stop_loss"] = nuevo_sl
                    print(f"  [TRAIL] {par}: SL -> ${nuevo_sl:,.4f}")

            cerrar = False
            razon  = ""
            if precio_actual <= op["stop_loss"]:
                cerrar = True
                razon  = f"Stop Loss (-{STOP_LOSS_PCT*100:.1f}%)"
            elif precio_actual >= op["take_profit"]:
                cerrar = True
                razon  = f"Take Profit (+{TAKE_PROFIT_PCT*100:.1f}%)"

            if cerrar:
                await self._cerrar_posicion(op, precio_actual, pnl_usdt, razon)

    async def _cerrar_posicion(self, op, precio_actual, pnl_usdt, razon):
        par = op["par"]
        ccy = par.split("-")[0]

        print(f"[CLOSE] {par}: {razon} | PnL: {pnl_usdt:+.2f} USDT")
        resultado = self.okx.place_market_sell_all(par, ccy)

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
                f"PnL acumulado: `{self.pnl_hoy:+.2f} USDT`"
            )
        else:
            print(f"[ERROR] No se pudo cerrar {par}: {resultado.get('error')}")
            await self.notifier.enviar(
                f"*Error cerrando {par}*\n`{resultado.get('error')}`"
            )

    async def enviar_reporte(self):
        balance_usdt  = self.okx.get_balance("USDT")
        balance_total = self.okx.get_total_balance_usdt()
        posiciones    = self.okx.get_posiciones_abiertas()
        total_trades  = self.trades_ganados + self.trades_perdidos
        winrate       = int((self.trades_ganados / total_trades) * 100) if total_trades > 0 else 0
        pnl_emoji     = "📈" if self.pnl_hoy >= 0 else "📉"

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
                lineas.append(
                    f"• {p['ccy']}: {p['cantidad']:.4f} = `${p['valor_usdt']:.2f}`"
                )

        if self.operaciones:
            lineas.append(f"\n*Trades activos:*")
            for op in self.operaciones:
                pnl = op.get("pnl_actual", 0)
                lineas.append(
                    f"• {op['par']} | ${op['precio_entrada']:,.4f} | "
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
            f"🎯 Winrate: {stats.get('winrate', 0)}%\n\n"
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