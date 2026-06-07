import time
import hmac
import hashlib
import base64
import json
import requests
from datetime import datetime, timezone

import sys
sys.path.insert(0, '.')
from config.settings import OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE, OKX_DEMO_MODE


class OKXConnector:

    BASE_URL = "https://www.okx.com"

    def __init__(self):
        self.api_key    = OKX_API_KEY
        self.secret_key = OKX_SECRET_KEY
        self.passphrase = OKX_PASSPHRASE
        self.demo_mode  = OKX_DEMO_MODE
        self.session    = requests.Session()
        modo = "DEMO" if self.demo_mode else "REAL"
        print(f"[INFO] OKX Connector iniciado en modo {modo}")

    def _get_timestamp(self):
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    def _sign(self, timestamp, method, path, body=""):
        message = f"{timestamp}{method.upper()}{path}{body}"
        mac = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode('utf-8')

    def _get_headers(self, method, path, body=""):
        ts = self._get_timestamp()
        headers = {
            "OK-ACCESS-KEY":        self.api_key,
            "OK-ACCESS-SIGN":       self._sign(ts, method, path, body),
            "OK-ACCESS-TIMESTAMP":  ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type":         "application/json",
        }
        if self.demo_mode:
            headers["x-simulated-trading"] = "1"
        return headers

    def _request(self, method, endpoint, params=None, data=None):
        url  = self.BASE_URL + endpoint
        body = json.dumps(data) if data else ""
        headers = self._get_headers(method, endpoint, body)
        for intento in range(3):
            try:
                if method == "GET":
                    resp = self.session.get(url, headers=headers, params=params, timeout=10)
                else:
                    resp = self.session.post(url, headers=headers, data=body, timeout=10)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                print(f"[WARNING] Intento {intento+1}/3 fallido: {e}")
                time.sleep(2 ** intento)
        return {"code": "-1", "msg": "Error de conexion", "data": []}

    def get_balance(self, currency="USDT"):
        resp = self._request("GET", "/api/v5/account/balance")
        try:
            for detail in resp["data"][0]["details"]:
                if detail["ccy"] == currency:
                    return float(detail["availBal"])
        except Exception:
            pass
        return 0.0

    def get_full_balance(self):
        resp = self._request("GET", "/api/v5/account/balance")
        balances = {}
        try:
            for detail in resp["data"][0]["details"]:
                if float(detail["cashBal"]) > 0:
                    balances[detail["ccy"]] = {
                        "disponible": float(detail["availBal"]),
                        "total":      float(detail["cashBal"]),
                    }
        except Exception:
            pass
        return balances

    def get_total_balance_usdt(self):
        """Retorna el valor total de la cuenta en USDT incluyendo todas las monedas."""
        resp = self._request("GET", "/api/v5/account/balance")
        try:
            return float(resp["data"][0]["totalEq"])
        except Exception:
            return self.get_balance("USDT")

    def get_price(self, par):
        resp = self._request("GET", "/api/v5/market/ticker", params={"instId": par})
        try:
            return float(resp["data"][0]["last"])
        except Exception:
            return 0.0

    def get_candles(self, par, timeframe="1H", limite=200):
        resp = self._request(
            "GET", "/api/v5/market/candles",
            params={"instId": par, "bar": timeframe, "limit": str(limite)}
        )
        velas = []
        try:
            for v in reversed(resp["data"]):
                velas.append({
                    "time":   datetime.fromtimestamp(int(v[0]) / 1000),
                    "open":   float(v[1]),
                    "high":   float(v[2]),
                    "low":    float(v[3]),
                    "close":  float(v[4]),
                    "volume": float(v[5]),
                })
        except Exception:
            pass
        return velas

    def get_24h_stats(self, par):
        resp = self._request("GET", "/api/v5/market/ticker", params={"instId": par})
        try:
            d = resp["data"][0]
            return {
                "par":          par,
                "precio":       float(d["last"]),
                "cambio_24h":   float(d["change24h"]) * 100,
                "alto_24h":     float(d["high24h"]),
                "bajo_24h":     float(d["low24h"]),
                "volumen_usdt": float(d["volCcy24h"]),
            }
        except Exception:
            return {}

    def get_instrument_info(self, par):
        """Obtiene info del par: tamaño mínimo, lot size, tick size."""
        resp = self._request("GET", "/api/v5/public/instruments",
                             params={"instType": "SPOT", "instId": par})
        try:
            return resp["data"][0]
        except Exception:
            return {}

    def place_market_order(self, par, lado, cantidad_usdt):
        precio = self.get_price(par)
        if precio == 0:
            return {"ok": False, "error": "No se pudo obtener precio"}

        # Obtener info del instrumento
        info    = self.get_instrument_info(par)
        min_sz  = float(info.get("minSz", "0.000001"))
        lot_sz  = float(info.get("lotSz", "0.000001"))

        # Calcular cantidad en crypto
        cantidad_crypto = cantidad_usdt / precio

        # Redondear al lot size correcto
        if lot_sz >= 1:
            cantidad_crypto = round(cantidad_crypto / lot_sz) * lot_sz
            cantidad_crypto = int(cantidad_crypto)
        else:
            decimales = len(str(lot_sz).rstrip('0').split('.')[-1]) if '.' in str(lot_sz) else 0
            cantidad_crypto = round(cantidad_crypto, decimales)

        # Verificar mínimo
        if cantidad_crypto < min_sz:
            cantidad_crypto = min_sz

        # Verificar que el valor en USDT sea suficiente
        valor_usdt = cantidad_crypto * precio
        if valor_usdt < 1.0:
            return {"ok": False, "error": f"Orden muy pequeña: ${valor_usdt:.4f} USDT"}

        data = {
            "instId":  par,
            "tdMode":  "cash",
            "side":    lado,
            "ordType": "market",
            "sz":      str(cantidad_crypto),
        }

        print(f"[INFO] Orden: {lado.upper()} {cantidad_crypto} {par} (~${valor_usdt:.2f} USDT)")
        resp = self._request("POST", "/api/v5/trade/order", data=data)

        try:
            if resp["code"] == "0":
                orden_id = resp["data"][0]["ordId"]
                print(f"[OK] Orden ejecutada. ID: {orden_id}")
                return {"ok": True, "orden_id": orden_id, "precio_ref": precio,
                        "cantidad_crypto": cantidad_crypto}
            else:
                error = resp.get("msg", "Error desconocido")
                if resp.get("data"):
                    error = resp["data"][0].get("sMsg", error)
                print(f"[ERROR] Error en orden: {error}")
                return {"ok": False, "error": error}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_order_history(self, limite=10):
        params = {"instType": "SPOT", "limit": str(limite)}
        resp = self._request("GET", "/api/v5/trade/orders-history", params=params)
        historial = []
        try:
            for o in resp.get("data", []):
                historial.append({
                    "orden_id":    o["ordId"],
                    "par":         o["instId"],
                    "lado":        o["side"],
                    "precio_exec": float(o["avgPx"]) if o["avgPx"] else 0,
                    "cantidad":    float(o["sz"]),
                    "pnl":         float(o["pnl"]) if o["pnl"] else 0,
                    "estado":      o["state"],
                    "ejecutada":   datetime.fromtimestamp(int(o["fillTime"]) / 1000) if o.get("fillTime") else None,
                })
        except Exception:
            pass
        return historial

    def get_posiciones_abiertas(self):
        """Obtiene todas las posiciones abiertas en spot."""
        resp = self._request("GET", "/api/v5/account/balance")
        posiciones = []
        try:
            for detail in resp["data"][0]["details"]:
                ccy   = detail["ccy"]
                total = float(detail["cashBal"])
                if ccy != "USDT" and total > 0:
                    par    = f"{ccy}-USDT"
                    precio = self.get_price(par)
                    if precio > 0:
                        valor_usdt = total * precio
                        if valor_usdt > 0.5:
                            posiciones.append({
                                "ccy":        ccy,
                                "par":        par,
                                "cantidad":   total,
                                "precio":     precio,
                                "valor_usdt": valor_usdt,
                            })
        except Exception:
            pass
        return posiciones

    def test_connection(self):
        print("[INFO] Probando conexion con OKX...")
        try:
            balance       = self.get_balance()
            balance_total = self.get_total_balance_usdt()
            modo          = "DEMO" if self.demo_mode else "REAL"
            print(f"[OK] Conexion exitosa | Modo: {modo} | USDT: ${balance:.2f} | Total: ${balance_total:.2f}")
            return True
        except Exception as e:
            print(f"[ERROR] Error de conexion: {e}")
            return False