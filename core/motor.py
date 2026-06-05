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
        self.capital         = CAPITAL_TOTAL_USD
        self.ciclo_num       = 0
        self.db              = Database()
        print("[INFO] Motor de trading iniciado")

    async def iniciar(self):
        self.activo = True
        print("[OK] Motor activo. Analizando mercado cada 30 minutos...")
        await self.notifier.enviar(
            "*Motor de trading activo*\n\n"
            f"Pares monitoreados: {len(TRADING_PAIRS)}\n"
            f"Capital: ${self.capital:.2f} USDT\n"
            f"Riesgo por trade: {MAX_RISK_PER_TRADE*100:.1f}%\n"
            f"Modo: CONFIANZA MEDIA-ALTA\n"
            f"Trailing Stop: {TRAILING_PCT*100:.1f}%\n"
            f"Analisis: 15m + 1H + 4H\n"
            "Analizando mercado cada 30 minutos..."
        )
        while self.activo:
            try:
                await self.ciclo()
            except Exception as e:
                print(f"[ERROR] Error en ciclo: {e}")
                await self.notifier.notificar_error(str(e))
            await asyncio.sleep(1800)

    async def ciclo(self):
        self.ciclo_num += 1
        print(f"\n[INFO] Ciclo #{self.ciclo_num}: {datetime.now().strftime('%H:%M:%S')}")
        await self.monitorear_posiciones()
        if not self.puede_abrir_trade():
            await self.enviar_reporte_horario()
            return
        mejor = await self.encontrar_mejor_oportunidad()
        if mejor:
            await self.ejecutar_trade(mejor)
        if self.ciclo_num % 2 == 0:
            await self.enviar_reporte_horario()

    async def enviar_reporte_horario(self):
        balance = self.okx.get_balance("USDT")
        ops     = len(self.operaciones)
        winrate = 0
        if (self.trades_ganados + self.trades_perdidos) > 0:
            winrate = int((self.trades_ganados / (self.trades_ganados + self.trades_perdidos)) * 100)
        stats     = self.db.get_estadisticas()
        pnl_emoji = "📈" if self.pnl_hoy >= 0 else "📉"
        await self.notifier.enviar(
            f"*Reporte hora #{self.ciclo_num}*\n"
            f"{datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            f"Balance: ${balance:,.2f} USDT\n"
            f"{pnl_emoji} PnL hoy: {'+'if self.pnl_hoy>=0 else ''}{self.pnl_hoy:.2f} USDT\n"
            f"PnL total: {'+'if self.pnl_total>=0 else ''}{self.pnl_total:.2f} USDT\n"
            f"Trades hoy: {self.trades_hoy}\n"
            f"Winrate total: {stats.get('winrate', 0)}%\n"
            f"Posiciones abiertas: {ops}\n\n"
            f"Proxima revision en 30 minutos"
        )

    async def enviar_reporte_diario(self):
        balance   = self.okx.get_balance("USDT")
        stats     = self.db.get_estadisticas()
        pnl_emoji = "📈" if self.pnl_hoy >= 0 else "📉"
        self.db.guardar_balance_diario(
            balance    = balance,
            pnl_dia    = self.pnl_hoy,
            trades_dia = self.trades_hoy,
            ganados    = self.trades_ganados,
            perdidos   = self.trades_perdidos,
        )
        await self.notifier.enviar(
            f"📊 *Reporte diario*\n"
            f"{datetime.now().strftime('%d/%m/%Y')}\n\n"
            f"Balance: ${balance:,.2f} USDT\n"
            f"{pnl_emoji} PnL hoy: {'+'if self.pnl_hoy>=0 else ''}{self.pnl_hoy:.2f} USDT\n"
            f"PnL total: {'+'if self.pnl_total>=0 else ''}{self.pnl_total:.2f} USDT\n\n"
            f"Trades hoy: {self.trades_hoy}\n"
            f"Ganados: {self.trades_ganados}\n"
            f"Perdidos: {self.trades_perdidos}\n"
            f"Winrate total: {stats.get('winrate', 0)}%\n\n"
            f"Mejor trade: +${stats.get('mejor_trade', 0):.2f}\n"
            f"Peor trade: ${stats.get('peor_trade', 0):.2f}\n"
            f"Total trades historico: {stats.get('total_trades', 0)}"
        )
        self.pnl_hoy         = 0.0
        self.trades_hoy      = 0
        self.trades_ganados  = 0
        self.trades_perdidos = 0

    def puede_abrir_trade(self):
        if len(self.operaciones) >= MAX_OPEN_TRADES:
            print(f"[INFO] Max trades abiertos ({MAX_OPEN_TRADES})")
            return False
        if self.pnl_hoy < -(self.capital * MAX_DAILY_LOSS):
            print("[WARNING] Limite de perdida diaria alcanzado. Bot pausado.")
            self.activo = False
            return False
        return True

    async def encontrar_mejor_oportunidad(self):
        print("[INFO] Escaneando pares (15m + 1H + 4H)...")
        mejores = []

        for par in TRADING_PAIRS:
            try:
                # Analisis 15 minutos
                velas_15m = self.okx.get_candles(par, "15m", 100)
                if len(velas_15m) < 50:
                    continue
                analisis_15m = Indicators.analisis_completo(velas_15m)
                if not analisis_15m:
                    continue

                # Analisis 1H
                velas_1h = self.okx.get_candles(par, "1H", 100)
                if len(velas_1h) < 50:
                    continue
                analisis_1h = Indicators.analisis_completo(velas_1h)
                if not analisis_1h:
                    continue

                # Analisis 4H
                velas_4h = self.okx.get_candles(par, "4H", 60)
                if len(velas_4h) < 50:
                    continue
                analisis_4h = Indicators.analisis_completo(velas_4h)
                if not analisis_4h:
                    continue

                señal_15m = analisis_15m["señal"]
                señal_1h  = analisis_1h["señal"]
                señal_4h  = analisis_4h["señal"]
                fuerza_15m = analisis_15m["fuerza"]
                fuerza_1h  = analisis_1h["fuerza"]
                fuerza_4h  = analisis_4h["fuerza"]
                rsi_1h     = analisis_1h["rsi"]
                rsi_4h     = analisis_4h["rsi"]

                # COMPRA: al menos 2 de 3 timeframes alineados
                señales_compra = sum([
                    1 for s in [señal_15m, señal_1h, señal_4h]
                    if s in ["COMPRA", "COMPRA_FUERTE"]
                ])
                fuerza_total   = fuerza_15m + fuerza_1h + fuerza_4h
                rsi_seguro     = rsi_1h < 65 and rsi_4h < 70
                tendencia_ok   = analisis_4h["tendencia"] in ["ALCISTA", "LATERAL"]
                fuerza_minima  = fuerza_total >= 4

                # VENTA: al menos 2 de 3 timeframes bajistas
                señales_venta = sum([
                    1 for s in [señal_15m, señal_1h, señal_4h]
                    if s in ["VENTA", "VENTA_FUERTE"]
                ])
                rsi_alto          = rsi_1h > 60 and rsi_4h > 55
                tendencia_bajista = analisis_4h["tendencia"] in ["BAJISTA", "LATERAL"]

                if señales_compra >= 2 and fuerza_minima and rsi_seguro and tendencia_ok:
                    confianza = min(99, int((fuerza_total / 15) * 100))
                    mejores.append({
                        "par":        par,
                        "analisis":   analisis_1h,
                        "analisis_4h": analisis_4h,
                        "lado":       "buy",
                        "fuerza":     fuerza_total,
                        "confianza":  confianza,
                    })
                    print(f"[COMPRA] {par}: F={fuerza_total} | RSI={rsi_1h}/{rsi_4h} | {señal_15m}/{señal_1h}/{señal_4h} | {confianza}%")

                elif señales_venta >= 2 and fuerza_minima and rsi_alto and tendencia_bajista:
                    confianza = min(99, int((abs(fuerza_total) / 15) * 100))
                    mejores.append({
                        "par":        par,
                        "analisis":   analisis_1h,
                        "analisis_4h": analisis_4h,
                        "lado":       "sell",
                        "fuerza":     fuerza_total,
                        "confianza":  confianza,
                    })
                    print(f"[VENTA] {par}: F={fuerza_total} | RSI={rsi_1h}/{rsi_4h} | {señal_15m}/{señal_1h}/{señal_4h} | {confianza}%")

                else:
                    print(f"[SKIP] {par}: {señal_15m}/{señal_1h}/{señal_4h} | F={fuerza_total}")

            except Exception as e:
                print(f"[WARNING] Error analizando {par}: {e}")

        if not mejores:
            print("[INFO] Sin oportunidades en este ciclo")
            return None

        mejores.sort(key=lambda x: x["fuerza"], reverse=True)
        elegido = mejores[0]
        print(f"[OK] Mejor: {elegido['par']} | {elegido['lado'].upper()} | {elegido['confianza']}%")
        return elegido

    async def ejecutar_trade(self, oportunidad):
        par       = oportunidad["par"]
        lado      = oportunidad["lado"]
        analisis  = oportunidad["analisis"]
        confianza = oportunidad["confianza"]

        pares_abiertos = [op["par"] for op in self.operaciones]
        if par in pares_abiertos:
            print(f"[SKIP] Ya hay operacion en {par}")
            return

        balance  = self.okx.get_balance("USDT")
        cantidad = balance * MAX_RISK_PER_TRADE
        if cantidad < MIN_ORDER_USDT:
            cantidad = MIN_ORDER_USDT
        if cantidad > balance * 0.95:
            print(f"[WARNING] Balance insuficiente: ${balance:.2f}")
            return

        precio = self.okx.get_price(par)
        if lado == "buy":
            stop_loss   = precio * (1 - STOP_LOSS_PCT)
            take_profit = precio * (1 + TAKE_PROFIT_PCT)
        else:
            stop_loss   = precio * (1 + STOP_LOSS_PCT)
            take_profit = precio * (1 - TAKE_PROFIT_PCT)

        razon = " | ".join(analisis["razones"][:3])

        await self.notifier.enviar(
            f"*Señal {lado.upper()}: {par}*\n\n"
            f"Confianza: {confianza}%\n"
            f"RSI 1H: {analisis['rsi']}\n"
            f"Tendencia: {analisis['tendencia']}\n"
            f"Razon: {razon}\n\n"
            f"Ejecutando orden..."
        )

        resultado = self.okx.place_market_order(par, lado, cantidad)

        if resultado["ok"]:
            op = {
                "orden_id":       resultado["orden_id"],
                "par":            par,
                "lado":           lado,
                "precio_entrada": precio,
                "tamaño_usdt":    cantidad,
                "stop_loss":      stop_loss,
                "take_profit":    take_profit,
                "trailing_max":   precio,
                "pnl_actual":     0.0,
                "abierta_en":     datetime.now(),
                "razon":          razon,
                "confianza":      confianza,
                "rsi":            analisis["rsi"],
                "tendencia":      analisis["tendencia"],
            }
            self.operaciones.append(op)
            self.trades_hoy += 1
            self.db.guardar_trade_abierto(op)
            await self.notifier.notificar_trade_abierto(
                par, lado, precio, cantidad, stop_loss, take_profit, razon
            )
        else:
            print(f"[ERROR] Trade fallido: {resultado.get('error')}")
            await self.notifier.enviar(f"*Error ejecutando trade*\n\n{resultado.get('error')}")

    async def monitorear_posiciones(self):
        if not self.operaciones:
            return
        for op in self.operaciones[:]:
            par            = op["par"]
            precio_actual  = self.okx.get_price(par)
            precio_entrada = op["precio_entrada"]
            lado           = op["lado"]

            if lado == "buy":
                pnl_pct = (precio_actual - precio_entrada) / precio_entrada
                if precio_actual > op["trailing_max"]:
                    op["trailing_max"] = precio_actual
                    nuevo_sl = precio_actual * (1 - TRAILING_PCT)
                    if nuevo_sl > op["stop_loss"]:
                        op["stop_loss"] = nuevo_sl
                        print(f"[TRAIL] {par}: SL subido a ${nuevo_sl:,.4f}")
            else:
                pnl_pct = (precio_entrada - precio_actual) / precio_entrada
                if precio_actual < op["trailing_max"]:
                    op["trailing_max"] = precio_actual
                    nuevo_sl = precio_actual * (1 + TRAILING_PCT)
                    if nuevo_sl < op["stop_loss"]:
                        op["stop_loss"] = nuevo_sl
                        print(f"[TRAIL] {par}: SL bajado a ${nuevo_sl:,.4f}")

            pnl_usdt         = pnl_pct * op["tamaño_usdt"]
            op["pnl_actual"] = pnl_usdt

            cerrar = False
            razon  = ""
            if lado == "buy":
                if precio_actual <= op["stop_loss"]:
                    cerrar = True
                    razon  = "Stop Loss activado"
                elif precio_actual >= op["take_profit"]:
                    cerrar = True
                    razon  = "Take Profit alcanzado"
            else:
                if precio_actual >= op["stop_loss"]:
                    cerrar = True
                    razon  = "Stop Loss activado"
                elif precio_actual <= op["take_profit"]:
                    cerrar = True
                    razon  = "Take Profit alcanzado"

            if cerrar:
                lado_cierre = "sell" if lado == "buy" else "buy"
                print(f"[INFO] Cerrando {par}: {razon} | PnL: {pnl_usdt:.2f} USDT")
                resultado = self.okx.place_market_order(par, lado_cierre, op["tamaño_usdt"])
                if resultado["ok"]:
                    self.pnl_hoy         += pnl_usdt
                    self.pnl_total       += pnl_usdt
                    if pnl_usdt >= 0:
                        self.trades_ganados += 1
                    else:
                        self.trades_perdidos += 1
                    self.db.cerrar_trade(op["orden_id"], precio_actual, pnl_usdt, razon)
                    self.operaciones.remove(op)
                    await self.notifier.notificar_trade_cerrado(
                        par, precio_entrada, precio_actual, pnl_usdt, razon
                    )

    def detener(self):
        self.activo = False
        print("[INFO] Motor detenido")