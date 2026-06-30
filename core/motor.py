import asyncio
from datetime import datetime, timedelta

import sys
sys.path.insert(0, '.')
from config.settings import (
    TRADING_PAIRS, CAPITAL_TOTAL_USD, MAX_RISK_PER_TRADE,
    MAX_OPEN_TRADES, MAX_DAILY_LOSS, STOP_LOSS_PCT,
    TAKE_PROFIT_PCT, MIN_ORDER_USDT, TRAILING_PCT,
    SCORE_MINIMO, FILTRO_MERCADO_PCT, BREAKEVEN_PCT
)
from utils.indicators import Indicators
from utils.database import Database

PARES_PRINCIPALES = ["BTC-USDT", "ETH-USDT"]
MAX_PERDIDAS_BLACKLIST = 3
HORAS_BLACKLIST = 24


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
        self.blacklist       = {}
        self.perdidas_par    = {}
        self.mercado_pausado = False
        self.ultimo_reporte_semanal = None
        print("[INFO] Motor profesional v3 iniciado")

    async def iniciar(self):
        self.activo = True
        balance     = self.okx.get_total_balance_usdt()
        print(f"[OK] Motor activo | Balance: ${balance:.2f} USDT")
        await self.notifier.enviar(
            f"Motor de trading activo v3\n\n"
            f"Balance: ${balance:.2f} USDT\n"
            f"Max trades simultaneos: {MAX_OPEN_TRADES}\n"
            f"Score minimo: {SCORE_MINIMO}\n"
            f"Stop Loss: {STOP_LOSS_PCT*100:.1f}% | Take Profit: {TAKE_PROFIT_PCT*100:.1f}%\n"
            f"Breakeven en: +{BREAKEVEN_PCT*100:.1f}%\n"
            f"Filtro mercado: -{FILTRO_MERCADO_PCT*100:.0f}%\n"
            f"Revision cada 15 minutos"
        )
        while self.activo:
            try:
                await self.ciclo()
            except Exception as e:
                print(f"[ERROR] Ciclo: {e}")
                await self.notifier.enviar(f"Error en ciclo\n{e}")
            await asyncio.sleep(900)

    async def ciclo(self):
        self.ciclo_num += 1
        ahora = datetime.now()
        print(f"\n{'='*50}")
        print(f"[CICLO #{self.ciclo_num}] {ahora.strftime('%d/%m/%Y %H:%M:%S')}")

        self._limpiar_blacklist()
        await self.monitorear_posiciones()

        # Verificar condicion de mercado
        mercado_ok = await self.verificar_mercado()

        if mercado_ok and self.puede_abrir_trade():
            await self.escanear_y_operar()

        if self.ciclo_num % 4 == 0:
            await self.enviar_reporte()

        if ahora.hour == 9 and ahora.minute < 15:
            await self.reporte_diario()

        if ahora.weekday() == 0 and ahora.hour == 9 and ahora.minute < 15:
            if self.ultimo_reporte_semanal != ahora.date():
                self.ultimo_reporte_semanal = ahora.date()
                await self.reporte_semanal()

    async def verificar_mercado(self):
        """
        Verifica si el mercado general está en caída fuerte.
        Si BTC cae más de FILTRO_MERCADO_PCT en 4H, pausa nuevas entradas.
        """
        try:
            velas_4h = self.okx.get_candles("BTC-USDT", "4H", 3)
            if len(velas_4h) < 2:
                return True
            precio_actual  = velas_4h[-1]["close"]
            precio_4h_atras = velas_4h[0]["close"]
            cambio_4h = (precio_actual - precio_4h_atras) / precio_4h_atras

            if cambio_4h < -FILTRO_MERCADO_PCT:
                if not self.mercado_pausado:
                    self.mercado_pausado = True
                    print(f"[FILTRO] Mercado en caida fuerte: {cambio_4h*100:.2f}%. Pausando entradas.")
                    await self.notifier.enviar(
                        f"Mercado en caida fuerte\n\n"
                        f"BTC bajo {cambio_4h*100:.2f}% en 4H\n"
                        f"Pausando nuevas entradas hasta que estabilice\n"
                        f"Posiciones actuales siguen monitoreadas"
                    )
                return False
            else:
                if self.mercado_pausado:
                    self.mercado_pausado = False
                    print(f"[FILTRO] Mercado estabilizado. Reanudando operaciones.")
                    await self.notifier.enviar(
                        f"Mercado estabilizado\n\n"
                        f"BTC: {cambio_4h*100:+.2f}% en 4H\n"
                        f"Reanudando busqueda de señales"
                    )
                return True
        except Exception as e:
            print(f"[WARNING] Error verificando mercado: {e}")
            return True

    def _limpiar_blacklist(self):
        ahora     = datetime.now()
        expirados = [par for par, exp in self.blacklist.items() if ahora >= exp]
        for par in expirados:
            del self.blacklist[par]
            self.perdidas_par[par] = 0
            print(f"[INFO] {par} removido de blacklist")
            asyncio.create_task(self.notifier.enviar(
                f"Par reactivado\n{par} vuelve a operar"
            ))

    def _registrar_perdida(self, par):
        self.perdidas_par[par] = self.perdidas_par.get(par, 0) + 1
        if self.perdidas_par[par] >= MAX_PERDIDAS_BLACKLIST:
            expira = datetime.now() + timedelta(hours=HORAS_BLACKLIST)
            self.blacklist[par] = expira
            print(f"[BLACKLIST] {par} bloqueado {HORAS_BLACKLIST}h")
            asyncio.create_task(self.notifier.enviar(
                f"Par en blacklist\n\n"
                f"{par} pausado {HORAS_BLACKLIST}h\n"
                f"Se reactiva: {expira.strftime('%d/%m %H:%M')}"
            ))

    def _registrar_ganancia(self, par):
        self.perdidas_par[par] = 0

    def puede_abrir_trade(self):
        if not self.activo:
            return False
        if len(self.operaciones) >= MAX_OPEN_TRADES:
            print(f"[INFO] Max trades: {len(self.operaciones)}/{MAX_OPEN_TRADES}")
            return False
        balance_usdt = self.okx.get_balance("USDT")
        if balance_usdt < MIN_ORDER_USDT:
            print(f"[INFO] USDT insuficiente: ${balance_usdt:.2f}")
            return False
        total       = self.okx.get_total_balance_usdt()
        perdida_pct = abs(self.pnl_hoy) / max(total, 1)
        if self.pnl_hoy < 0 and perdida_pct > MAX_DAILY_LOSS:
            print(f"[WARNING] Perdida diaria maxima alcanzada")
            self.activo = False
            asyncio.create_task(self.notifier.enviar(
                f"Bot pausado\n\n"
                f"Perdida diaria maxima: {perdida_pct*100:.1f}%\n"
                f"Usa /iniciar manana"
            ))
            return False
        return True

    def calcular_tamano(self):
        balance_usdt  = self.okx.get_balance("USDT")
        balance_total = self.okx.get_total_balance_usdt()
        tamano = balance_total * MAX_RISK_PER_TRADE
        tamano = min(tamano, balance_usdt * 0.90)
        if tamano < MIN_ORDER_USDT:
            if balance_usdt >= MIN_ORDER_USDT:
                tamano = MIN_ORDER_USDT
            else:
                return 0
        return round(tamano, 2)

    async def escanear_y_operar(self):
        pares_libres = [p for p in PARES_PRINCIPALES
                        if p not in [op["par"] for op in self.operaciones]
                        and p not in self.blacklist]

        print(f"[SCAN] Analizando {len(pares_libres)} pares | Score minimo: {SCORE_MINIMO}")

        candidatos = []
        for par in pares_libres:
            try:
                señal = self.analizar_par(par)
                if señal:
                    candidatos.append(señal)
                    print(f"  [SIGNAL] {par}: {señal['tipo']} | Score={señal['score']:.0f} | RSI={señal['rsi']:.0f}")
                else:
                    pass
            except Exception as e:
                print(f"  [ERROR] {par}: {e}")

        if not candidatos:
            print("[INFO] Sin señales de calidad en este ciclo")
            return

        # Ordenar por score y tomar el mejor
        candidatos.sort(key=lambda x: x["score"], reverse=True)
        mejor  = candidatos[0]
        tamano = self.calcular_tamano()

        if tamano > 0:
            print(f"[OK] Ejecutando: {mejor['par']} | Score={mejor['score']} | ${tamano:.2f}")
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

        # ESTRATEGIA 1: RSI sobreventa — mayor peso
        if rsi_1h < 25:
            score += 60
            tipo   = "RSI_SOBREVENTA_EXTREMA"
            razon.append(f"RSI 1H extremo: {rsi_1h:.0f}")
        elif rsi_1h < 32:
            score += 40
            tipo   = "RSI_SOBREVENTA"
            razon.append(f"RSI 1H sobreventa: {rsi_1h:.0f}")
        elif rsi_1h < 40:
            score += 20
            tipo   = "RSI_BAJO"
            razon.append(f"RSI 1H bajo: {rsi_1h:.0f}")

        if rsi_15m < 25:
            score += 25
            razon.append(f"RSI 15m extremo: {rsi_15m:.0f}")
        elif rsi_15m < 35:
            score += 15
            razon.append(f"RSI 15m bajo: {rsi_15m:.0f}")

        # RSI 4H confirma la sobreventa
        if rsi_4h < 35:
            score += 20
            razon.append(f"RSI 4H bajo: {rsi_4h:.0f}")
        elif rsi_4h < 45:
            score += 10

        # ESTRATEGIA 2: Bollinger
        if boll_1h["posicion"] == "SOBREVENTA":
            score += 25
            tipo   = tipo or "BOLLINGER_INFERIOR"
            razon.append("Banda inferior Bollinger")
        elif boll_1h["posicion"] == "ZONA_BAJA":
            score += 10
            razon.append("Zona baja Bollinger")

        # ESTRATEGIA 3: MACD
        if macd_1h.get("cruce_alcista"):
            score += 20
            tipo   = tipo or "MACD_CRUCE"
            razon.append("MACD cruce alcista")

        # ESTRATEGIA 4: Tendencia
        if tendencia == "ALCISTA":
            score += 15
            tipo   = tipo or "TREND"
            razon.append("Tendencia alcista")
        elif tendencia == "LATERAL":
            score += 5

        # ESTRATEGIA 5: Multitimeframe
        if compras_count == 3:
            score += 20
            razon.append("3 TF alineados")
        elif compras_count == 2:
            score += 10
            razon.append("2 TF alineados")

        # FILTROS DE PROTECCION
        if rsi_1h > 65:
            return None  # Sobrecomprado — no entrar
        if rsi_4h > 70:
            return None  # Sobrecomprado en 4H — no entrar
        if tendencia == "BAJISTA" and rsi_1h > 45:
            score -= 25  # Bajista sin sobreventa — penalizar fuerte
        if tendencia == "BAJISTA" and compras_count == 0:
            return None  # Bajista sin ninguna señal — no entrar

        # Solo operar con score alto
        if score < SCORE_MINIMO or not tipo:
            return None

        return {
            "par":       par,
            "tipo":      tipo,
            "score":     score,
            "rsi":       rsi_1h,
            "rsi_4h":    rsi_4h,
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
        breakeven   = precio * (1 + BREAKEVEN_PCT)
        razon_str   = " | ".join(razones)

        print(f"[TRADE] COMPRA {par} | ${tamano:.2f} | Score={score}")
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
                "stop_loss":      precio_real * (1 - STOP_LOSS_PCT),
                "take_profit":    precio_real * (1 + TAKE_PROFIT_PCT),
                "breakeven":      precio_real * (1 + BREAKEVEN_PCT),
                "trailing_max":   precio_real,
                "breakeven_activo": False,
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
                f"COMPRA ejecutada\n\n"
                f"Par: {par}\n"
                f"Estrategia: {tipo} (Score: {score})\n"
                f"Precio: ${precio_real:,.4f}\n"
                f"Tamano: ${valor_real:.2f} USDT\n"
                f"Stop Loss: ${op['stop_loss']:,.4f} (-{STOP_LOSS_PCT*100:.1f}%)\n"
                f"Take Profit: ${op['take_profit']:,.4f} (+{TAKE_PROFIT_PCT*100:.1f}%)\n"
                f"Breakeven en: ${op['breakeven']:,.4f} (+{BREAKEVEN_PCT*100:.1f}%)\n"
                f"RSI 1H: {rsi:.0f} | Tendencia: {señal['tendencia']}\n"
                f"Razon: {razon_str}"
            )
        else:
            error = resultado.get("error", "Error desconocido")
            print(f"[ERROR] {par}: {error}")
            await self.notifier.enviar(f"Error en trade {par}\n{error}")

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

            # Breakeven — mover SL a precio de entrada cuando sube BREAKEVEN_PCT
            if not op.get("breakeven_activo") and precio_actual >= op.get("breakeven", float('inf')):
                op["stop_loss"]        = precio_entrada * 1.001  # SL ligeramente sobre entrada
                op["breakeven_activo"] = True
                print(f"  [BREAKEVEN] {par}: SL movido a entrada ${op['stop_loss']:,.4f}")
                await self.notifier.enviar(
                    f"Breakeven activado\n\n"
                    f"{par}: SL movido a entrada\n"
                    f"Ganancia garantizada desde aqui"
                )

            # Trailing stop
            if precio_actual > op["trailing_max"]:
                op["trailing_max"] = precio_actual
                nuevo_sl = precio_actual * (1 - TRAILING_PCT)
                if nuevo_sl > op["stop_loss"]:
                    op["stop_loss"] = nuevo_sl
                    print(f"  [TRAIL] {par}: SL -> ${nuevo_sl:,.4f}")

            # Verificar cierre
            cerrar = False
            razon  = ""
            if precio_actual <= op["stop_loss"]:
                cerrar = True
                if op.get("breakeven_activo"):
                    razon = "Trailing Stop (breakeven)"
                else:
                    razon = f"Stop Loss (-{STOP_LOSS_PCT*100:.1f}%)"
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
                emoji = "GANANCIA"
                self._registrar_ganancia(par)
            else:
                self.trades_perdidos += 1
                emoji = "PERDIDA"
                self._registrar_perdida(par)

            duracion = int((datetime.now() - op["abierta_en"]).total_seconds() / 60)
            pct      = (pnl_usdt / op["tamaño_usdt"]) * 100

            self.db.cerrar_trade(op["orden_id"], precio_actual, pnl_usdt, razon)
            self.operaciones.remove(op)

            await self.notifier.enviar(
                f"{emoji}\n\n"
                f"Par: {par}\n"
                f"Entrada: ${op['precio_entrada']:,.4f}\n"
                f"Salida:  ${precio_actual:,.4f}\n"
                f"PnL: {pnl_usdt:+.2f} USDT ({pct:+.2f}%)\n"
                f"Duracion: {duracion} min\n"
                f"Razon: {razon}\n"
                f"PnL acumulado hoy: {self.pnl_hoy:+.2f} USDT"
            )
        else:
            print(f"[ERROR] No se pudo cerrar {par}: {resultado.get('error')}")
            await self.notifier.enviar(f"Error cerrando {par}\n{resultado.get('error')}")

    async def enviar_reporte(self):
        balance_usdt  = self.okx.get_balance("USDT")
        balance_total = self.okx.get_total_balance_usdt()
        posiciones    = self.okx.get_posiciones_abiertas()
        total_trades  = self.trades_ganados + self.trades_perdidos
        winrate       = int((self.trades_ganados / total_trades) * 100) if total_trades > 0 else 0
        roi           = ((balance_total - CAPITAL_TOTAL_USD) / CAPITAL_TOTAL_USD) * 100
        ahora         = datetime.now().strftime('%d/%m/%Y %H:%M')

        tend_emoji = "📈" if self.pnl_hoy > 0 else ("📉" if self.pnl_hoy < 0 else "➡️")
        mercado_txt = "PAUSADO (caida fuerte)" if self.mercado_pausado else "ACTIVO"

        lineas = [
            f"REPORTE | {ahora}\n",
            f"Balance:    ${balance_total:,.2f} USDT",
            f"USDT libre: ${balance_usdt:,.2f}",
            f"ROI total:  {roi:+.2f}%\n",
            f"{tend_emoji} PnL hoy:   {self.pnl_hoy:+.2f} USDT",
            f"PnL total:  {self.pnl_total:+.2f} USDT\n",
            f"Trades hoy: {self.trades_hoy}",
            f"Ganados:    {self.trades_ganados}",
            f"Perdidos:   {self.trades_perdidos}",
            f"Winrate:    {winrate}%\n",
            f"Mercado:    {mercado_txt}",
        ]

        if self.blacklist:
            bl_pares = ", ".join(self.blacklist.keys())
            lineas.append(f"Blacklist:  {bl_pares}")

        if self.operaciones:
            lineas.append(f"\nPOSICIONES ABIERTAS ({len(self.operaciones)})")
            lineas.append("─────────────────────")
            for op in self.operaciones:
                pnl        = op.get("pnl_actual", 0)
                precio_act = self.okx.get_price(op["par"])
                pct        = ((precio_act - op["precio_entrada"]) / op["precio_entrada"]) * 100
                duracion   = int((datetime.now() - op["abierta_en"]).total_seconds() / 60)
                horas      = duracion // 60
                mins       = duracion % 60
                dur_txt    = f"{horas}h {mins}m" if horas > 0 else f"{mins}m"
                dist_tp    = ((op["take_profit"] - precio_act) / precio_act) * 100
                dist_sl    = ((precio_act - op["stop_loss"]) / precio_act) * 100
                be_txt     = " BE" if op.get("breakeven_activo") else ""

                if pnl > op["tamaño_usdt"] * 0.03:
                    estado = "Ganando bien"
                elif pnl > 0:
                    estado = "En ganancia"
                elif pnl < -op["tamaño_usdt"] * 0.015:
                    estado = "Cerca del SL"
                else:
                    estado = "En perdida"

                lineas.append(
                    f"\n{op['par']}{be_txt} — {estado}\n"
                    f"${op['precio_entrada']:,.4f} → ${precio_act:,.4f} ({pct:+.2f}%)\n"
                    f"PnL: {pnl:+.2f} USDT | Tiempo: {dur_txt}\n"
                    f"TP: +{dist_tp:.2f}% | SL: -{dist_sl:.2f}%"
                )
        elif posiciones:
            lineas.append(f"\nEN OKX ({len(posiciones)} activos)")
            for p in posiciones:
                lineas.append(f"• {p['ccy']}: ${p['valor_usdt']:.2f}")
        else:
            lineas.append("\nSin posiciones — buscando señales...")

        await self.notifier.enviar("\n".join(lineas))

    async def reporte_diario(self):
        balance_total = self.okx.get_total_balance_usdt()
        stats         = self.db.get_estadisticas()
        roi           = ((balance_total - CAPITAL_TOTAL_USD) / CAPITAL_TOTAL_USD) * 100

        self.db.guardar_balance_diario(
            balance    = balance_total,
            pnl_dia    = self.pnl_hoy,
            trades_dia = self.trades_hoy,
            ganados    = self.trades_ganados,
            perdidos   = self.trades_perdidos,
        )

        await self.notifier.enviar(
            f"REPORTE DIARIO\n"
            f"{datetime.now().strftime('%d/%m/%Y')}\n\n"
            f"Balance: ${balance_total:,.2f} USDT\n"
            f"ROI total: {roi:+.2f}%\n"
            f"PnL hoy: {self.pnl_hoy:+.2f} USDT\n"
            f"PnL acumulado: {self.pnl_total:+.2f} USDT\n\n"
            f"Trades hoy: {self.trades_hoy}\n"
            f"Ganados: {self.trades_ganados}\n"
            f"Perdidos: {self.trades_perdidos}\n"
            f"Winrate total: {stats.get('winrate', 0)}%\n\n"
            f"Mejor trade: +${stats.get('mejor_trade', 0):.2f}\n"
            f"Peor trade: ${stats.get('peor_trade', 0):.2f}\n"
            f"Total historico: {stats.get('total_trades', 0)} trades"
        )

        self.pnl_hoy         = 0.0
        self.trades_hoy      = 0
        self.trades_ganados  = 0
        self.trades_perdidos = 0

    async def reporte_semanal(self):
        balance_total = self.okx.get_total_balance_usdt()
        stats         = self.db.get_estadisticas()
        stats_par     = self.db.get_stats_por_par()
        roi           = ((balance_total - CAPITAL_TOTAL_USD) / CAPITAL_TOTAL_USD) * 100

        lineas = [
            f"REPORTE SEMANAL\n"
            f"{(datetime.now()-timedelta(days=7)).strftime('%d/%m')} — {datetime.now().strftime('%d/%m/%Y')}\n",
            f"Balance: ${balance_total:,.2f} USDT",
            f"ROI total: {roi:+.2f}%",
            f"PnL acumulado: {self.pnl_total:+.2f} USDT\n",
            f"Total trades: {stats.get('total_trades', 0)}",
            f"Ganados: {stats.get('ganados', 0)}",
            f"Perdidos: {stats.get('perdidos', 0)}",
            f"Winrate: {stats.get('winrate', 0)}%\n",
            f"Mejor trade: +${stats.get('mejor_trade', 0):.2f}",
            f"Peor trade: ${stats.get('peor_trade', 0):.2f}",
        ]

        if stats_par:
            lineas.append("\nRENDIMIENTO POR PAR")
            lineas.append("─────────────────────")
            for par, data in sorted(stats_par.items(), key=lambda x: x[1]['pnl'], reverse=True):
                emoji = "+" if data['pnl'] >= 0 else ""
                lineas.append(
                    f"{par}: {emoji}{data['pnl']:.2f} USDT "
                    f"({data['ganados']}G/{data['perdidos']}P)"
                )

        await self.notifier.enviar("\n".join(lineas))

    def detener(self):
        self.activo = False
        print("[INFO] Motor detenido")