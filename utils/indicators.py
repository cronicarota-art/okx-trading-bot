import pandas as pd
import numpy as np

class Indicators:

    @staticmethod
    def rsi(closes, period=14):
        closes = pd.Series(closes)
        delta = closes.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 2)

    @staticmethod
    def macd(closes, fast=12, slow=26, signal=9):
        closes = pd.Series(closes)
        ema_fast = closes.ewm(span=fast, adjust=False).mean()
        ema_slow = closes.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return {
            "macd":      round(float(macd_line.iloc[-1]), 6),
            "signal":    round(float(signal_line.iloc[-1]), 6),
            "histogram": round(float(histogram.iloc[-1]), 6),
            "cruce_alcista": (macd_line.iloc[-1] > signal_line.iloc[-1] and
                              macd_line.iloc[-2] <= signal_line.iloc[-2]),
            "cruce_bajista": (macd_line.iloc[-1] < signal_line.iloc[-1] and
                              macd_line.iloc[-2] >= signal_line.iloc[-2]),
        }

    @staticmethod
    def bollinger(closes, period=20, std=2.0):
        closes = pd.Series(closes)
        sma = closes.rolling(window=period).mean()
        desv = closes.rolling(window=period).std()
        upper = sma + (desv * std)
        lower = sma - (desv * std)
        precio_actual = closes.iloc[-1]
        banda_superior = float(upper.iloc[-1])
        banda_inferior = float(lower.iloc[-1])
        banda_media   = float(sma.iloc[-1])
        ancho = (banda_superior - banda_inferior) / banda_media
        if precio_actual <= banda_inferior:
            posicion = "SOBREVENTA"
        elif precio_actual >= banda_superior:
            posicion = "SOBRECOMPRA"
        else:
            pct = (precio_actual - banda_inferior) / (banda_superior - banda_inferior)
            if pct < 0.3:
                posicion = "ZONA_BAJA"
            elif pct > 0.7:
                posicion = "ZONA_ALTA"
            else:
                posicion = "NEUTRAL"
        return {
            "superior":  round(banda_superior, 4),
            "media":     round(banda_media, 4),
            "inferior":  round(banda_inferior, 4),
            "posicion":  posicion,
            "ancho":     round(ancho, 4),
        }

    @staticmethod
    def ema(closes, period=20):
        closes = pd.Series(closes)
        ema = closes.ewm(span=period, adjust=False).mean()
        return round(float(ema.iloc[-1]), 4)

    @staticmethod
    def tendencia(closes, periodo_corto=20, periodo_largo=50):
        if len(closes) < periodo_largo:
            return "NEUTRAL"
        ema_corta = pd.Series(closes).ewm(span=periodo_corto, adjust=False).mean().iloc[-1]
        ema_larga = pd.Series(closes).ewm(span=periodo_largo, adjust=False).mean().iloc[-1]
        if ema_corta > ema_larga * 1.002:
            return "ALCISTA"
        elif ema_corta < ema_larga * 0.998:
            return "BAJISTA"
        else:
            return "LATERAL"

    @staticmethod
    def volumen_alto(volumes, periodo=20):
        volumes = pd.Series(volumes)
        promedio = volumes.rolling(window=periodo).mean().iloc[-1]
        actual   = volumes.iloc[-1]
        return actual > promedio * 1.5

    @staticmethod
    def analisis_completo(velas):
        if len(velas) < 50:
            return None
        closes  = [v["close"]  for v in velas]
        volumes = [v["volume"] for v in velas]
        rsi_val  = Indicators.rsi(closes)
        macd_val = Indicators.macd(closes)
        boll_val = Indicators.bollinger(closes)
        tend_val = Indicators.tendencia(closes)
        vol_alto = Indicators.volumen_alto(volumes)
        señal = "ESPERAR"
        fuerza = 0
        razones = []

        if rsi_val < 30:
            fuerza += 2
            razones.append(f"RSI sobreventa ({rsi_val})")
        elif rsi_val < 40:
            fuerza += 1
            razones.append(f"RSI bajo ({rsi_val})")
        elif rsi_val > 70:
            fuerza -= 2
            razones.append(f"RSI sobrecompra ({rsi_val})")
        elif rsi_val > 60:
            fuerza -= 1
            razones.append(f"RSI alto ({rsi_val})")

        if macd_val["cruce_alcista"]:
            fuerza += 2
            razones.append("MACD cruce alcista")
        elif macd_val["cruce_bajista"]:
            fuerza -= 2
            razones.append("MACD cruce bajista")
        elif macd_val["macd"] > macd_val["signal"]:
            fuerza += 1
            razones.append("MACD positivo")
        else:
            fuerza -= 1
            razones.append("MACD negativo")

        if boll_val["posicion"] == "SOBREVENTA":
            fuerza += 2
            razones.append("Precio en banda inferior Bollinger")
        elif boll_val["posicion"] == "SOBRECOMPRA":
            fuerza -= 2
            razones.append("Precio en banda superior Bollinger")
        elif boll_val["posicion"] == "ZONA_BAJA":
            fuerza += 1
            razones.append("Precio en zona baja Bollinger")

        if tend_val == "ALCISTA":
            fuerza += 1
            razones.append("Tendencia alcista")
        elif tend_val == "BAJISTA":
            fuerza -= 1
            razones.append("Tendencia bajista")

        if vol_alto and fuerza > 0:
            fuerza += 1
            razones.append("Volumen alto confirma")

        if fuerza >= 4:
            señal = "COMPRA_FUERTE"
        elif fuerza >= 2:
            señal = "COMPRA"
        elif fuerza <= -4:
            señal = "VENTA_FUERTE"
        elif fuerza <= -2:
            señal = "VENTA"
        else:
            señal = "ESPERAR"

        return {
            "señal":      señal,
            "fuerza":     fuerza,
            "razones":    razones,
            "rsi":        rsi_val,
            "macd":       macd_val,
            "bollinger":  boll_val,
            "tendencia":  tend_val,
            "volumen_alto": vol_alto,
        }