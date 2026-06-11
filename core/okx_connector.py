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
        self._instrument_cache = {}
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
        return {
            "OK-ACCESS-KEY":        self.api_key,
            "OK-ACCESS-SIGN":       self._sign(ts, method, path, body),
            "OK-ACCESS-TIMESTAMP":  ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type":         "application/json",
        }

    def _request(self, method, endpoint, params=None, data=None):
        url  = self.BASE_URL + endpoint
        body = json.dumps(data) if data else ""
        headers = self._get_headers(method, endpoint, body)
        for intento in range(3):
            try:
                if method == "GET":
                    resp = self.session.get(url, headers=headers, params=params, timeout=15)
                else:
                    resp = self.session.post(url, headers=headers, data=body, timeout=15)
                resp.raise_for_status()
                resultado = resp.json()
                if resultado.get("code") not in ["0", 0]:
                    print(f"[OKX ERROR] {resultado.get('msg')} | code: {resultado.get('code')}")
                return resultado
            except Exception as e:
                print(f"[WARNING] Intento {intento+1}/3: {e}")
                time.sleep(2 ** intento)
        return {"code": "-1", "msg": "Max reintentos", "data": []}

    def get_balance(self, currency="USDT"):
        resp = self._request("GET", "/api/v5/account/balance")
        try:
            for d in resp["data"][0]["details"]:
                if d["ccy"] == currency:
                    return float(d["availBal"])
        except Exception:
            pass
        return 0.0

    def get_total_balance_usdt(self):
        resp = self._request("GET", "/api/v5/account/balance")
        try:
            return float(resp["data"][0]["totalEq"])
        except Exception:
            return self.get_balance()

    def get_full_balance(self):
        resp = self._request("GET", "/api/v5/account/balance")
        result = {}
        try:
            for d in resp["data"][0]["details"]:
                total = float(d["cashBal"])
                if total > 0:
                    result[d["ccy"]] = {
                        "disponible": float(d["availBal"]),
                        "total":      total,
                    }
        except Exception:
            pass
        return result

    def get_posiciones_abiertas(self):
        resp = self._request("GET", "/api/v5/account/balance")
        posiciones = []
        try:
            for d in resp["data"][0]["details"]:
                ccy   = d["ccy"]
                total = float(d["cashBal"])
                if ccy != "USDT" and total > 0.0001:
                    par    = f"{ccy}-USDT"
                    precio = self.get_price(par)
                    if precio > 0:
                        valor = total * precio
                        if valor > 0.5:
                            posiciones.append({
                                "ccy":        ccy,
                                "par":        par,
                                "cantidad":   total,
                                "precio":     precio,
                                "valor_usdt": valor,
                            })
        except Exception:
            pass
        return posiciones

    def get_price(self, par):
        resp = self._request("GET", "/api/v5/market/ticker", params={"instId": par})
        try:
            return float(resp["data"][0]["last"])
        except Exception:
            return 0.0

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

    def get_candles(self, par, timeframe="1H", limite=200):
        resp = self._request("GET", "/api/v5/market/candles",
                             params={"instId": par, "bar": timeframe, "limit": str(limite)})
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

    def get_instrument_info(self, par):
        if par in self._instrument_cache:
            return self._instrument_cache[par]
        resp = self._request("GET", "/api/v5/public/instruments",
                             params={"instType": "SPOT", "instId": par})
        try:
            info = resp["data"][0]
            self._instrument_cache[par] = info
            return info
        except Exception:
            return {}

    def place_market_order(self, par, lado, cantidad_usdt):
        """
        Ejecuta orden de mercado especificando el monto en USDT directamente.
        Usa tgtCcy=quote_ccy para que OKX calcule la cantidad de crypto.
        """
        precio = self.get_price(par)
        if precio == 0:
            return {"ok": False, "error": "No se pudo obtener precio"}

        sz = str(round(float(cantidad_usdt), 2))

        data = {
            "instId":  par,
            "tdMode":  "cash",
            "side":    lado,
            "ordType": "market",
            "sz":      sz,
            "tgtCcy":  "quote_ccy",
        }

        print(f"[INFO] Orden {lado.upper()}: ${cantidad_usdt:.2f} USDT en {par}")
        resp = self._request("POST", "/api/v5/trade/order", data=data)

        try:
            if resp["code"] == "0":
                orden_id = resp["data"][0]["ordId"]
                print(f"[OK] Orden ejecutada ID: {orden_id}")
                return {
                    "ok":         True,
                    "orden_id":   orden_id,
                    "precio_ref": precio,
                    "valor_usdt": cantidad_usdt,
                }
            else:
                error = resp.get("msg", "Error desconocido")
                if resp.get("data"):
                    error = resp["data"][0].get("sMsg", error)
                print(f"[ERROR] Orden fallida: {error}")
                return {"ok": False, "error": error}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def place_market_sell_all(self, par, ccy):
        """Vende toda la cantidad disponible de una moneda."""
        balance = self.get_balance(ccy)
        if balance <= 0:
            return {"ok": False, "error": f"No hay {ccy} disponible"}

        info   = self.get_instrument_info(par)
        min_sz = float(info.get("minSz", "0.000001"))
        lot_sz = float(info.get("lotSz", "0.000001"))

        import math
        if lot_sz >= 1:
            cantidad = int(math.floor(balance / lot_sz) * lot_sz)
        else:
            decimales = max(0, -int(math.floor(math.log10(lot_sz))))
            cantidad  = round(math.floor(balance / lot_sz) * lot_sz, decimales)

        if cantidad < min_sz:
            return {"ok": False, "error": f"Cantidad insuficiente: {balance} {ccy}"}

        if cantidad < 0.001:
            sz_str = f"{cantidad:.8f}".rstrip('0')
        else:
            sz_str = str(cantidad)

        data = {
            "instId":  par,
            "tdMode":  "cash",
            "side":    "sell",
            "ordType": "market",
            "sz":      sz_str,
        }

        print(f"[INFO] Venta total: {cantidad} {ccy}")
        resp = self._request("POST", "/api/v5/trade/order", data=data)

        try:
            if resp["code"] == "0":
                orden_id = resp["data"][0]["ordId"]
                return {"ok": True, "orden_id": orden_id, "cantidad": cantidad}
            else:
                error = resp.get("msg", "Error")
                if resp.get("data"):
                    error = resp["data"][0].get("sMsg", error)
                return {"ok": False, "error": error}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_order_history(self, limite=20):
        params = {"instType": "SPOT", "limit": str(limite)}
        resp   = self._request("GET", "/api/v5/trade/orders-history", params=params)
        result = []
        try:
            for o in resp.get("data", []):
                result.append({
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
        return result

    def test_connection(self):
        print("[INFO] Probando conexion con OKX...")
        try:
            usdt  = self.get_balance()
            total = self.get_total_balance_usdt()
            modo  = "DEMO" if self.demo_mode else "REAL"
            print(f"[OK] Conexion exitosa | {modo} | USDT: ${usdt:.2f} | Total: ${total:.2f}")
            return True
        except Exception as e:
            print(f"[ERROR] {e}")
            return False