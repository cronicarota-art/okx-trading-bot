import sys
import asyncio
from datetime import datetime


def test_conexion():
    print("=" * 45)
    print("  MODO DE PRUEBA - Verificando conexiones")
    print("=" * 45)
    from config.settings import OKX_API_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    if OKX_API_KEY == "TU_API_KEY_AQUI":
        print("[WARNING] OKX: API keys NO configuradas aun")
    else:
        print("[INFO] Probando OKX...")
        from core.okx_connector import OKXConnector
        okx = OKXConnector()
        ok  = okx.test_connection()
        if ok:
            precio_btc = okx.get_price("BTC-USDT")
            print(f"[OK] OKX conectado | Precio BTC: ${precio_btc:,.2f}")
        else:
            print("[ERROR] No se pudo conectar con OKX")
    if TELEGRAM_TOKEN == "TU_TOKEN_DE_TELEGRAM_AQUI":
        print("[WARNING] Telegram: Token NO configurado aun")
    else:
        print(f"[OK] Telegram configurado | Chat ID: {TELEGRAM_CHAT_ID}")
    print("=" * 45)
    print("Prueba completada.")
    print("=" * 45)


def iniciar_bot():
    from config.settings import OKX_API_KEY, TELEGRAM_TOKEN, OKX_DEMO_MODE, CAPITAL_TOTAL_USD
    modo = "DEMO" if OKX_DEMO_MODE else "REAL"
    print("=" * 45)
    print("  OKX TRADING BOT v1.0")
    print(f"  Modo: {modo}")
    print(f"  Capital: ${CAPITAL_TOTAL_USD:,.2f} USDT")
    print("=" * 45)

    if OKX_API_KEY == "TU_API_KEY_AQUI":
        print("[ERROR] Configura tus API keys en config/settings.py")
        sys.exit(1)
    if TELEGRAM_TOKEN == "TU_TOKEN_DE_TELEGRAM_AQUI":
        print("[ERROR] Configura tu token de Telegram en config/settings.py")
        sys.exit(1)

    print("[INFO] Conectando con OKX...")
    from core.okx_connector import OKXConnector
    okx = OKXConnector()
    if not okx.test_connection():
        print("[ERROR] No se pudo conectar con OKX")
        sys.exit(1)

    print("[INFO] Iniciando bot de Telegram...")
    from core.telegram_bot import crear_app_telegram, bot_estado, TelegramNotifier
    app      = crear_app_telegram()
    notifier = TelegramNotifier(app)

    print("[INFO] Iniciando motor de trading...")
    from core.motor import Motor
    motor = Motor(okx, notifier)

    print("[INFO] Iniciando panel web...")
    from panel import iniciar_panel
    iniciar_panel(motor=motor, okx=okx, puerto=8080)

    bot_estado["okx"]     = okx
    bot_estado["motor"]   = motor
    bot_estado["balance"] = okx.get_balance()

    print("[OK] Todo listo. Bot corriendo...")
    print("[INFO] Panel web: http://localhost:8080")
    print("[INFO] Controla el bot desde Telegram con /start")
    print("[INFO] Presiona Ctrl+C para detener")

    async def reporte_diario_loop():
        while True:
            ahora = datetime.now()
            if ahora.hour == 9 and ahora.minute == 0:
                print("[INFO] Enviando reporte diario...")
                await motor.enviar_reporte_diario()
            await asyncio.sleep(60)

    async def arrancar():
        async with app:
            await app.initialize()
            await notifier.enviar(
                f"*Bot OKX iniciado*\n\n"
                f"Modo: {modo}\n"
                f"Balance: ${bot_estado['balance']:,.2f} USDT\n"
                f"Usa /iniciar para activar el trading\n\n"
                f"{datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            asyncio.create_task(reporte_diario_loop())
            await asyncio.Event().wait()

    asyncio.run(arrancar())


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--test" in args:
        test_conexion()
    else:
        iniciar_bot()