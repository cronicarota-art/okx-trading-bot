from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio

import sys
sys.path.insert(0, '.')
from config.settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ALLOWED_USERS, OKX_DEMO_MODE, CAPITAL_TOTAL_USD

bot_estado = {
    "activo":      False,
    "pausado":     False,
    "operaciones": [],
    "balance":     0.0,
    "pnl_hoy":     0.0,
    "pnl_total":   0.0,
    "trades_hoy":  0,
    "okx":         None,
    "motor":       None,
}

def autorizado(user_id):
    permitidos = [int(TELEGRAM_CHAT_ID)] + [int(u) for u in TELEGRAM_ALLOWED_USERS]
    return user_id in permitidos

def modo_badge():
    return "DEMO" if OKX_DEMO_MODE else "REAL"

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    teclado = [
        [InlineKeyboardButton("Iniciar Bot",    callback_data="iniciar"),
         InlineKeyboardButton("Estado",         callback_data="estado")],
        [InlineKeyboardButton("Balance",        callback_data="balance"),
         InlineKeyboardButton("Operaciones",    callback_data="operaciones")],
        [InlineKeyboardButton("Rendimiento",    callback_data="rendimiento"),
         InlineKeyboardButton("Config",         callback_data="config")],
    ]
    await update.message.reply_text(
        f"OKX Trading Bot v2.0 | {modo_badge()}\n\n"
        f"Comandos disponibles:\n"
        f"/estado — Estado del bot\n"
        f"/balance — Saldo en OKX\n"
        f"/iniciar — Activar trading\n"
        f"/pausar — Pausar bot\n"
        f"/detener — Detener todo\n"
        f"/operaciones — Trades abiertos\n"
        f"/historial — Ultimos trades\n"
        f"/rendimiento — PnL y estadisticas\n"
        f"/analisis BTC — Analisis tecnico\n"
        f"/cerrar DOGE — Cerrar posicion\n"
        f"/modo normal — Cambiar modo\n"
        f"/config — Configuracion actual",
        reply_markup=InlineKeyboardMarkup(teclado)
    )

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    motor  = bot_estado.get("motor")
    estado = "ACTIVO" if (motor and motor.activo) else "INACTIVO"
    bal    = motor.okx.get_total_balance_usdt() if motor and motor.okx else 0
    ops    = len(motor.operaciones) if motor else 0
    pnl    = motor.pnl_hoy if motor else 0
    roi    = ((bal - CAPITAL_TOTAL_USD) / CAPITAL_TOTAL_USD) * 100

    texto = (
        f"Estado del Bot | {modo_badge()}\n\n"
        f"Estado: {estado}\n"
        f"Balance total: ${bal:,.2f} USDT\n"
        f"ROI total: {roi:+.2f}%\n"
        f"PnL hoy: {pnl:+.2f} USDT\n"
        f"Trades hoy: {motor.trades_hoy if motor else 0}\n"
        f"Posiciones abiertas: {ops}\n\n"
        f"Panel: https://worker-production-e4fa.up.railway.app\n"
        f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )
    teclado = [[
        InlineKeyboardButton("Actualizar", callback_data="estado"),
        InlineKeyboardButton("Balance",    callback_data="balance"),
    ]]
    if update.callback_query:
        await update.callback_query.edit_message_text(
            texto,
            reply_markup=InlineKeyboardMarkup(teclado)
        )
    else:
        await update.message.reply_text(
            texto,
            reply_markup=InlineKeyboardMarkup(teclado)
        )

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg = update.message or update.callback_query.message
    await msg.reply_text("Consultando balance en OKX...")
    try:
        okx = bot_estado.get("okx")
        if not okx:
            from core.okx_connector import OKXConnector
            okx = OKXConnector()

        balance_usdt  = okx.get_balance("USDT")
        balance_total = okx.get_total_balance_usdt()
        posiciones    = okx.get_posiciones_abiertas()
        roi           = ((balance_total - CAPITAL_TOTAL_USD) / CAPITAL_TOTAL_USD) * 100

        lineas = [f"Balance OKX | {modo_badge()}\n"]
        lineas.append(f"USDT disponible: ${balance_usdt:,.2f}")
        lineas.append(f"Valor total: ${balance_total:,.2f} USDT")
        lineas.append(f"ROI total: {roi:+.2f}%\n")

        if posiciones:
            lineas.append("Posiciones abiertas:")
            for p in posiciones:
                lineas.append(f"• {p['ccy']}: {p['cantidad']:.4f} = ${p['valor_usdt']:.2f}")

        await msg.reply_text("\n".join(lineas))
    except Exception as e:
        await msg.reply_text(f"Error: {e}")

async def cmd_iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg   = update.message or update.callback_query.message
    motor = bot_estado.get("motor")
    if motor and motor.activo:
        await msg.reply_text("El bot ya esta activo.")
        return
    bot_estado["activo"]  = True
    bot_estado["pausado"] = False
    await msg.reply_text(
        f"Bot iniciado | {modo_badge()}\n\n"
        f"Capital: ${CAPITAL_TOTAL_USD:,.2f} USDT\n"
        f"Analizando mercado..."
    )
    if motor:
        asyncio.create_task(motor.iniciar())

async def cmd_pausar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg = update.message or update.callback_query.message
    motor = bot_estado.get("motor")
    if motor:
        motor.detener()
    await msg.reply_text("Bot pausado\nUsa /iniciar para reanudar.")

async def cmd_detener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg = update.message or update.callback_query.message
    motor = bot_estado.get("motor")
    if motor:
        motor.detener()
    await msg.reply_text("Bot detenido.")

async def cmd_operaciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg   = update.message or update.callback_query.message
    motor = bot_estado.get("motor")
    okx   = bot_estado.get("okx")
    ops   = motor.operaciones if motor else []
    pos   = okx.get_posiciones_abiertas() if okx else []

    if not ops and not pos:
        await msg.reply_text("No hay posiciones abiertas.")
        return

    lineas = []
    if ops:
        lineas.append(f"Trades activos del bot ({len(ops)})\n")
        for i, op in enumerate(ops, 1):
            pnl    = op.get("pnl_actual", 0)
            precio = okx.get_price(op["par"]) if okx else 0
            pct    = ((precio - op["precio_entrada"]) / op["precio_entrada"]) * 100 if op["precio_entrada"] > 0 else 0
            estado = "Ganando bien" if pnl > op["tamaño_usdt"]*0.02 else ("Cerca SL" if pnl < -op["tamaño_usdt"]*0.015 else "En ganancia" if pnl > 0 else "En perdida")
            lineas.append(
                f"{i}. {op['par']} — {estado}\n"
                f"Entrada: ${op['precio_entrada']:,.4f} | Actual: ${precio:,.4f}\n"
                f"PnL: {pnl:+.2f} USDT ({pct:+.2f}%)\n"
                f"SL: ${op['stop_loss']:,.4f} | TP: ${op['take_profit']:,.4f}\n"
            )

    if pos:
        lineas.append(f"Posiciones en OKX ({len(pos)})")
        for p in pos:
            lineas.append(f"• {p['ccy']}: {p['cantidad']:.4f} = ${p['valor_usdt']:.2f}")

    await msg.reply_text("\n".join(lineas))

async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg = update.message or update.callback_query.message
    motor = bot_estado.get("motor")
    if not motor:
        await msg.reply_text("Bot no iniciado.")
        return
    trades = motor.db.get_trades_historial(10)
    if not trades:
        await msg.reply_text("Sin historial aun.")
        return
    lineas = [f"Ultimos {len(trades)} trades\n"]
    for t in trades:
        resultado = "GANANCIA" if t.pnl_usdt > 0 else "PERDIDA"
        lineas.append(
            f"{resultado} | {t.par} | {t.pnl_usdt:+.2f} USDT\n"
            f"{t.razon_salida} | {t.duracion_min} min\n"
        )
    await msg.reply_text("\n".join(lineas))

async def cmd_rendimiento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg   = update.message or update.callback_query.message
    motor = bot_estado.get("motor")
    okx   = bot_estado.get("okx")

    bal      = okx.get_total_balance_usdt() if okx else 0
    roi      = ((bal - CAPITAL_TOTAL_USD) / CAPITAL_TOTAL_USD) * 100
    stats    = motor.db.get_estadisticas() if motor else {}
    pnl_hoy  = motor.pnl_hoy if motor else 0
    ganados  = motor.trades_ganados if motor else 0
    perdidos = motor.trades_perdidos if motor else 0

    await msg.reply_text(
        f"Rendimiento del Bot\n\n"
        f"Balance total: ${bal:,.2f} USDT\n"
        f"ROI total: {roi:+.2f}%\n"
        f"PnL hoy: {pnl_hoy:+.2f} USDT\n"
        f"PnL acumulado: {motor.pnl_total if motor else 0:+.2f} USDT\n\n"
        f"Trades hoy: {motor.trades_hoy if motor else 0}\n"
        f"Ganados hoy: {ganados}\n"
        f"Perdidos hoy: {perdidos}\n"
        f"Winrate total: {stats.get('winrate', 0)}%\n\n"
        f"Mejor trade: +${stats.get('mejor_trade', 0):.2f}\n"
        f"Peor trade: ${stats.get('peor_trade', 0):.2f}\n"
        f"Total historico: {stats.get('total_trades', 0)} trades"
    )

async def cmd_analisis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    args = context.args
    par  = args[0].upper() + "-USDT" if args else "BTC-USDT"
    if "-USDT" not in par:
        par = par + "-USDT"

    await update.message.reply_text(f"Analizando {par}...")
    try:
        okx   = bot_estado.get("okx")
        motor = bot_estado.get("motor")
        if not okx or not motor:
            await update.message.reply_text("Bot no iniciado.")
            return

        from utils.indicators import Indicators
        velas_15m = okx.get_candles(par, "15m", 100)
        velas_1h  = okx.get_candles(par, "1H",  100)
        velas_4h  = okx.get_candles(par, "4H",  60)

        a15m = Indicators.analisis_completo(velas_15m)
        a1h  = Indicators.analisis_completo(velas_1h)
        a4h  = Indicators.analisis_completo(velas_4h)

        precio = okx.get_price(par)
        señal  = motor.analizar_par(par)

        if señal:
            señal_txt = f"SEÑAL DE COMPRA | Score: {señal['score']} | {señal['tipo']}"
        else:
            señal_txt = "Sin señal en este momento"

        await update.message.reply_text(
            f"Analisis Tecnico: {par}\n\n"
            f"Precio actual: ${precio:,.4f}\n\n"
            f"RSI:\n"
            f"15m: {a15m['rsi']:.1f} — {a15m['señal']}\n"
            f"1H:  {a1h['rsi']:.1f} — {a1h['señal']}\n"
            f"4H:  {a4h['rsi']:.1f} — {a4h['señal']}\n\n"
            f"Tendencia 4H: {a4h['tendencia']}\n\n"
            f"MACD 1H:\n"
            f"Valor: {a1h['macd']['macd']:.4f}\n"
            f"Signal: {a1h['macd']['signal']:.4f}\n"
            f"Cruce alcista: {a1h['macd'].get('cruce_alcista', False)}\n\n"
            f"Bollinger 1H: {a1h['bollinger']['posicion']}\n\n"
            f"Senal: {señal_txt}"
        )
    except Exception as e:
        await update.message.reply_text(f"Error en analisis: {e}")

async def cmd_cerrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Uso: /cerrar DOGE")
        return
    ccy   = args[0].upper()
    par   = ccy + "-USDT"
    motor = bot_estado.get("motor")
    okx   = bot_estado.get("okx")

    if not motor or not okx:
        await update.message.reply_text("Bot no iniciado.")
        return

    op = next((o for o in motor.operaciones if o["par"] == par), None)
    if not op:
        await update.message.reply_text(f"No hay posicion abierta en {par}.")
        return

    await update.message.reply_text(f"Cerrando posicion en {par}...")
    precio = okx.get_price(par)
    pnl    = ((precio - op["precio_entrada"]) / op["precio_entrada"]) * op["tamaño_usdt"]
    resultado = okx.place_market_sell_all(par, ccy)

    if resultado["ok"]:
        motor.pnl_hoy   += pnl
        motor.pnl_total += pnl
        motor.db.cerrar_trade(op["orden_id"], precio, pnl, "Cierre manual")
        motor.operaciones.remove(op)
        await update.message.reply_text(
            f"Posicion cerrada manualmente\n\n"
            f"Par: {par}\n"
            f"PnL: {pnl:+.2f} USDT"
        )
    else:
        await update.message.reply_text(f"Error: {resultado.get('error')}")

async def cmd_modo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Uso: /modo conservador | normal | agresivo")
        return
    modo = args[0].lower()
    modos = {
        "conservador": {"stop": 0.015, "tp": 0.02,  "trailing": 0.01},
        "normal":      {"stop": 0.02,  "tp": 0.04,  "trailing": 0.015},
        "agresivo":    {"stop": 0.03,  "tp": 0.06,  "trailing": 0.02},
    }
    if modo not in modos:
        await update.message.reply_text("Modos disponibles: conservador, normal, agresivo")
        return
    import config.settings as s
    cfg = modos[modo]
    s.STOP_LOSS_PCT   = cfg["stop"]
    s.TAKE_PROFIT_PCT = cfg["tp"]
    s.TRAILING_PCT    = cfg["trailing"]
    await update.message.reply_text(
        f"Modo cambiado: {modo.upper()}\n\n"
        f"Stop Loss: {cfg['stop']*100:.1f}%\n"
        f"Take Profit: {cfg['tp']*100:.1f}%\n"
        f"Trailing Stop: {cfg['trailing']*100:.1f}%"
    )

async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    from config.settings import STOP_LOSS_PCT, TAKE_PROFIT_PCT, MAX_RISK_PER_TRADE, TRADING_PAIRS, TRAILING_PCT
    pares = ", ".join(TRADING_PAIRS)
    await update.message.reply_text(
        f"Configuracion actual\n\n"
        f"Modo: {modo_badge()}\n"
        f"Capital: ${CAPITAL_TOTAL_USD:,.2f}\n"
        f"Riesgo por trade: {MAX_RISK_PER_TRADE*100:.0f}%\n"
        f"Stop Loss: {STOP_LOSS_PCT*100:.1f}%\n"
        f"Take Profit: {TAKE_PROFIT_PCT*100:.1f}%\n"
        f"Trailing Stop: {TRAILING_PCT*100:.1f}%\n\n"
        f"Pares: {pares}\n\n"
        f"Panel: https://worker-production-e4fa.up.railway.app"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acciones = {
        "estado":      cmd_estado,
        "balance":     cmd_balance,
        "operaciones": cmd_operaciones,
        "iniciar":     cmd_iniciar,
        "rendimiento": cmd_rendimiento,
        "config":      cmd_config,
    }
    accion = acciones.get(query.data)
    if accion:
        await accion(update, context)


class TelegramNotifier:
    def __init__(self, app):
        self.app     = app
        self.chat_id = TELEGRAM_CHAT_ID

    async def enviar(self, mensaje):
        try:
            await self.app.bot.send_message(
                chat_id = self.chat_id,
                text    = mensaje,
            )
        except Exception as e:
            print(f"[ERROR] Telegram: {e}")

    async def notificar_trade_abierto(self, par, lado, precio, cantidad_usdt, stop_loss, take_profit, razon):
        lado_txt = "COMPRA" if lado == "buy" else "VENTA"
        await self.enviar(
            f"{lado_txt} ejecutada\n\n"
            f"Par: {par}\n"
            f"Precio: ${precio:,.4f}\n"
            f"Tamano: ${cantidad_usdt:.2f} USDT\n"
            f"SL: ${stop_loss:,.4f} | TP: ${take_profit:,.4f}\n"
            f"Razon: {razon}"
        )

    async def notificar_trade_cerrado(self, par, precio_entrada, precio_salida, pnl, razon):
        resultado = "GANANCIA" if pnl >= 0 else "PERDIDA"
        pct = ((precio_salida - precio_entrada) / precio_entrada) * 100
        await self.enviar(
            f"{resultado}\n\n"
            f"Par: {par}\n"
            f"Entrada: ${precio_entrada:,.4f}\n"
            f"Salida: ${precio_salida:,.4f}\n"
            f"PnL: {pnl:+.2f} USDT ({pct:+.2f}%)"
        )

    async def notificar_error(self, error):
        await self.enviar(f"Error del bot\n{error}")


def crear_app_telegram():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("estado",      cmd_estado))
    app.add_handler(CommandHandler("balance",     cmd_balance))
    app.add_handler(CommandHandler("iniciar",     cmd_iniciar))
    app.add_handler(CommandHandler("pausar",      cmd_pausar))
    app.add_handler(CommandHandler("detener",     cmd_detener))
    app.add_handler(CommandHandler("operaciones", cmd_operaciones))
    app.add_handler(CommandHandler("historial",   cmd_historial))
    app.add_handler(CommandHandler("rendimiento", cmd_rendimiento))
    app.add_handler(CommandHandler("analisis",    cmd_analisis))
    app.add_handler(CommandHandler("cerrar",      cmd_cerrar))
    app.add_handler(CommandHandler("modo",        cmd_modo))
    app.add_handler(CommandHandler("config",      cmd_config))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("[OK] Bot de Telegram configurado correctamente")
    return app