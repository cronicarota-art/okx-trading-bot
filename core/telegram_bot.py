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
        await update.message.reply_text("No autorizado.")
        return
    teclado = [
        [InlineKeyboardButton("Iniciar Bot", callback_data="iniciar"),
         InlineKeyboardButton("Estado",      callback_data="estado")],
        [InlineKeyboardButton("Balance",     callback_data="balance"),
         InlineKeyboardButton("Trades",      callback_data="operaciones")],
    ]
    await update.message.reply_text(
        f"*OKX Trading Bot* | Modo: {modo_badge()}\n\n"
        f"/estado - Estado del bot\n"
        f"/balance - Ver saldo en OKX\n"
        f"/iniciar - Activar trading\n"
        f"/pausar - Pausar bot\n"
        f"/detener - Detener todo\n"
        f"/operaciones - Trades abiertos\n"
        f"/historial - Ultimos trades\n"
        f"/rendimiento - PnL y estadisticas\n"
        f"/config - Configuracion actual",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(teclado)
    )

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    estado = "ACTIVO" if bot_estado["activo"] else ("PAUSADO" if bot_estado["pausado"] else "INACTIVO")
    pnl    = bot_estado["pnl_hoy"]
    texto  = (
        f"*Estado del Bot* | {modo_badge()}\n\n"
        f"Estado: {estado}\n"
        f"Balance: ${bot_estado['balance']:,.2f} USDT\n"
        f"PnL hoy: {'+'if pnl>=0 else ''}{pnl:.2f} USDT\n"
        f"PnL total: {'+'if bot_estado['pnl_total']>=0 else ''}{bot_estado['pnl_total']:.2f} USDT\n"
        f"Trades hoy: {bot_estado['trades_hoy']}\n"
        f"Posiciones abiertas: {len(bot_estado['operaciones'])}\n\n"
        f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )
    teclado = [[
        InlineKeyboardButton("Actualizar", callback_data="estado"),
        InlineKeyboardButton("Balance",    callback_data="balance"),
    ]]
    if update.callback_query:
        await update.callback_query.edit_message_text(texto, parse_mode="Markdown",
              reply_markup=InlineKeyboardMarkup(teclado))
    else:
        await update.message.reply_text(texto, parse_mode="Markdown",
              reply_markup=InlineKeyboardMarkup(teclado))

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
        balance_completo = okx.get_full_balance()
        balance_usdt     = okx.get_balance("USDT")
        if not balance_completo:
            await msg.reply_text("No se pudo obtener el balance. Verifica tus API keys.")
            return
        lineas = [f"*Balance OKX* | {modo_badge()}\n"]
        for moneda, datos in balance_completo.items():
            lineas.append(f"*{moneda}*: {datos['disponible']:.6f} disponible")
        lineas.append(f"\nUSDT disponible: ${balance_usdt:,.2f}")
        bot_estado["balance"] = balance_usdt
        await msg.reply_text("\n".join(lineas), parse_mode="Markdown")
    except Exception as e:
        await msg.reply_text(f"Error: {e}")

async def cmd_iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg = update.message or update.callback_query.message
    if bot_estado["activo"]:
        await msg.reply_text("El bot ya esta activo.")
        return
    bot_estado["activo"]  = True
    bot_estado["pausado"] = False
    await msg.reply_text(
        f"*Bot iniciado* | Modo: {modo_badge()}\n\n"
        f"Capital: ${CAPITAL_TOTAL_USD:,.2f} USDT\n"
        f"Analizando mercado...",
        parse_mode="Markdown"
    )
    motor = bot_estado.get("motor")
    if motor:
        asyncio.create_task(motor.iniciar())

async def cmd_pausar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg = update.message or update.callback_query.message
    bot_estado["activo"]  = False
    bot_estado["pausado"] = True
    motor = bot_estado.get("motor")
    if motor:
        motor.detener()
    await msg.reply_text("*Bot pausado*\nUsa /iniciar para reanudar.", parse_mode="Markdown")

async def cmd_detener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg = update.message or update.callback_query.message
    bot_estado["activo"]  = False
    bot_estado["pausado"] = False
    motor = bot_estado.get("motor")
    if motor:
        motor.detener()
    await msg.reply_text("*Bot detenido*\nTrading automatico desactivado.", parse_mode="Markdown")

async def cmd_operaciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg = update.message or update.callback_query.message
    motor = bot_estado.get("motor")
    ops   = motor.operaciones if motor else []
    if not ops:
        await msg.reply_text("No hay posiciones abiertas actualmente.")
        return
    lineas = [f"*Operaciones abiertas* ({len(ops)})\n"]
    for i, op in enumerate(ops, 1):
        pnl = op.get("pnl_actual", 0)
        lineas.append(
            f"#{i} {op['par']} - {op['lado'].upper()}\n"
            f"Entrada: ${op['precio_entrada']:,.4f}\n"
            f"PnL: {'+'if pnl>=0 else ''}{pnl:.2f} USDT\n"
            f"Confianza: {op.get('confianza', 0)}%\n"
        )
    await msg.reply_text("\n".join(lineas), parse_mode="Markdown")

async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg = update.message or update.callback_query.message
    await msg.reply_text("Obteniendo historial de OKX...")
    try:
        okx = bot_estado.get("okx")
        if not okx:
            from core.okx_connector import OKXConnector
            okx = OKXConnector()
        historial = okx.get_order_history(limite=10)
        if not historial:
            await msg.reply_text("No hay trades en el historial aun.")
            return
        lineas = [f"*Ultimos {len(historial)} trades*\n"]
        for t in historial:
            pnl   = t.get("pnl", 0)
            signo = "+" if pnl >= 0 else ""
            fecha = t["ejecutada"].strftime("%d/%m %H:%M") if t["ejecutada"] else "-"
            lineas.append(f"{t['par']} {t['lado'].upper()} | ${t['precio_exec']:,.4f} | {signo}{pnl:.4f} | {fecha}")
        await msg.reply_text("\n".join(lineas), parse_mode="Markdown")
    except Exception as e:
        await msg.reply_text(f"Error: {e}")

async def cmd_rendimiento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    msg = update.message or update.callback_query.message
    motor     = bot_estado.get("motor")
    pnl_total = bot_estado["pnl_total"]
    pnl_hoy   = motor.pnl_hoy if motor else 0.0
    trades    = motor.trades_hoy if motor else 0
    roi       = (pnl_total / CAPITAL_TOTAL_USD) * 100
    await msg.reply_text(
        f"*Rendimiento del Bot*\n\n"
        f"PnL hoy: {'+'if pnl_hoy>=0 else ''}{pnl_hoy:.2f} USDT\n"
        f"PnL total: {'+'if pnl_total>=0 else ''}{pnl_total:.2f} USDT\n"
        f"ROI: {'+'if roi>=0 else ''}{roi:.2f}%\n"
        f"Trades hoy: {trades}\n"
        f"Capital: ${CAPITAL_TOTAL_USD:,.2f}\n"
        f"Balance actual: ${bot_estado['balance']:,.2f}",
        parse_mode="Markdown"
    )

async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not autorizado(update.effective_user.id):
        return
    from config.settings import STOP_LOSS_PCT, TAKE_PROFIT_PCT, MAX_RISK_PER_TRADE, TRADING_PAIRS
    pares = "\n".join([f"  {p}" for p in TRADING_PAIRS])
    await update.message.reply_text(
        f"*Configuracion actual*\n\n"
        f"Modo: {modo_badge()}\n"
        f"Capital: ${CAPITAL_TOTAL_USD:,.2f}\n"
        f"Riesgo por trade: {MAX_RISK_PER_TRADE*100:.1f}%\n"
        f"Stop Loss: {STOP_LOSS_PCT*100:.1f}%\n"
        f"Take Profit: {TAKE_PROFIT_PCT*100:.1f}%\n\n"
        f"Pares monitoreados:\n{pares}",
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acciones = {
        "estado":      cmd_estado,
        "balance":     cmd_balance,
        "operaciones": cmd_operaciones,
        "iniciar":     cmd_iniciar,
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
                chat_id=self.chat_id,
                text=mensaje,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"[ERROR] Error enviando notificacion: {e}")

    async def notificar_trade_abierto(self, par, lado, precio, cantidad_usdt, stop_loss, take_profit, razon):
        emoji = "COMPRA" if lado == "buy" else "VENTA"
        await self.enviar(
            f"*{emoji} ejecutado*\n\n"
            f"Par: {par}\n"
            f"Precio: ${precio:,.4f}\n"
            f"Tamano: ${cantidad_usdt:.2f} USDT\n"
            f"Stop Loss: ${stop_loss:,.4f}\n"
            f"Take Profit: ${take_profit:,.4f}\n"
            f"Razon: {razon}\n"
            f"{datetime.now().strftime('%H:%M:%S')}"
        )

    async def notificar_trade_cerrado(self, par, precio_entrada, precio_salida, pnl, razon):
        resultado = "GANANCIA" if pnl >= 0 else "PERDIDA"
        pct = ((precio_salida - precio_entrada) / precio_entrada) * 100
        await self.enviar(
            f"*{resultado}*\n\n"
            f"Par: {par}\n"
            f"Entrada: ${precio_entrada:,.4f}\n"
            f"Salida: ${precio_salida:,.4f}\n"
            f"Cambio: {'+'if pct>=0 else ''}{pct:.2f}%\n"
            f"PnL: {'+'if pnl>=0 else ''}{pnl:.2f} USDT"
        )

    async def notificar_error(self, error):
        await self.enviar(f"*Error del bot*\n\n{error}")

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
    app.add_handler(CommandHandler("config",      cmd_config))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("[OK] Bot de Telegram configurado correctamente")
    return app