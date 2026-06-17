import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

import sys
sys.path.insert(0, '.')
from config.settings import DB_PATH

Base = declarative_base()


class TradeAbierto(Base):
    __tablename__ = "trades_abiertos"
    id             = Column(Integer, primary_key=True)
    orden_id       = Column(String, unique=True)
    par            = Column(String)
    lado           = Column(String)
    precio_entrada = Column(Float)
    tamano_usdt    = Column(Float)
    stop_loss      = Column(Float)
    take_profit    = Column(Float)
    trailing_max   = Column(Float)
    razon          = Column(Text)
    confianza      = Column(Integer)
    rsi            = Column(Float)
    tendencia      = Column(String)
    abierta_en     = Column(DateTime, default=datetime.now)


class TradeCerrado(Base):
    __tablename__ = "trades_cerrados"
    id             = Column(Integer, primary_key=True)
    orden_id       = Column(String)
    par            = Column(String)
    lado           = Column(String)
    precio_entrada = Column(Float)
    precio_salida  = Column(Float)
    tamano_usdt    = Column(Float)
    pnl_usdt       = Column(Float)
    duracion_min   = Column(Integer)
    razon_salida   = Column(String)
    confianza      = Column(Integer)
    rsi            = Column(Float)
    tendencia      = Column(String)
    abierta_en     = Column(DateTime)
    cerrada_en     = Column(DateTime, default=datetime.now)


class BalanceDiario(Base):
    __tablename__ = "balance_diario"
    id         = Column(Integer, primary_key=True)
    fecha      = Column(DateTime, default=datetime.now)
    balance    = Column(Float)
    pnl_dia    = Column(Float)
    trades_dia = Column(Integer)
    ganados    = Column(Integer)
    perdidos   = Column(Integer)


class Database:

    def __init__(self):
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.engine  = create_engine(f"sqlite:///{DB_PATH}", echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        print("[OK] Base de datos iniciada")

    def guardar_trade_abierto(self, op):
        try:
            s = self.Session()
            t = TradeAbierto(
                orden_id       = op["orden_id"],
                par            = op["par"],
                lado           = op["lado"],
                precio_entrada = op["precio_entrada"],
                tamano_usdt    = op["tamaño_usdt"],
                stop_loss      = op["stop_loss"],
                take_profit    = op["take_profit"],
                trailing_max   = op["trailing_max"],
                razon          = op.get("razon", ""),
                confianza      = op.get("confianza", 0),
                rsi            = op.get("rsi", 0),
                tendencia      = op.get("tendencia", ""),
                abierta_en     = op.get("abierta_en", datetime.now()),
            )
            s.merge(t)
            s.commit()
            s.close()
        except Exception as e:
            print(f"[DB] Error guardar trade: {e}")

    def cerrar_trade(self, orden_id, precio_salida, pnl_usdt, razon):
        try:
            s     = self.Session()
            trade = s.query(TradeAbierto).filter_by(orden_id=orden_id).first()
            if trade:
                duracion = int((datetime.now() - trade.abierta_en).total_seconds() / 60)
                cerrado  = TradeCerrado(
                    orden_id       = orden_id,
                    par            = trade.par,
                    lado           = trade.lado,
                    precio_entrada = trade.precio_entrada,
                    precio_salida  = precio_salida,
                    tamano_usdt    = trade.tamano_usdt,
                    pnl_usdt       = pnl_usdt,
                    duracion_min   = duracion,
                    razon_salida   = razon,
                    confianza      = trade.confianza,
                    rsi            = trade.rsi,
                    tendencia      = trade.tendencia,
                    abierta_en     = trade.abierta_en,
                    cerrada_en     = datetime.now(),
                )
                s.add(cerrado)
                s.delete(trade)
                s.commit()
            s.close()
        except Exception as e:
            print(f"[DB] Error cerrar trade: {e}")

    def get_trades_historial(self, limite=50):
        try:
            s      = self.Session()
            trades = s.query(TradeCerrado).order_by(
                TradeCerrado.cerrada_en.desc()
            ).limit(limite).all()
            s.close()
            return trades
        except Exception:
            return []

    def get_estadisticas(self):
        try:
            s      = self.Session()
            trades = s.query(TradeCerrado).all()
            s.close()
            if not trades:
                return {"winrate": 0, "mejor_trade": 0, "peor_trade": 0, "total_trades": 0}
            pnls     = [t.pnl_usdt for t in trades]
            ganados  = sum(1 for p in pnls if p > 0)
            total    = len(trades)
            winrate  = int((ganados / total) * 100) if total > 0 else 0
            return {
                "winrate":      winrate,
                "mejor_trade":  max(pnls),
                "peor_trade":   min(pnls),
                "total_trades": total,
                "ganados":      ganados,
                "perdidos":     total - ganados,
            }
        except Exception:
            return {"winrate": 0, "mejor_trade": 0, "peor_trade": 0, "total_trades": 0}

    def get_stats_por_par(self):
        try:
            s      = self.Session()
            trades = s.query(TradeCerrado).all()
            s.close()
            pares = {}
            for t in trades:
                if t.par not in pares:
                    pares[t.par] = {"ganados": 0, "perdidos": 0, "pnl": 0.0}
                if t.pnl_usdt > 0:
                    pares[t.par]["ganados"] += 1
                else:
                    pares[t.par]["perdidos"] += 1
                pares[t.par]["pnl"] += t.pnl_usdt
            return pares
        except Exception:
            return {}

    def guardar_balance_diario(self, balance, pnl_dia, trades_dia, ganados, perdidos):
        try:
            s = self.Session()
            b = BalanceDiario(
                balance    = balance,
                pnl_dia    = pnl_dia,
                trades_dia = trades_dia,
                ganados    = ganados,
                perdidos   = perdidos,
            )
            s.add(b)
            s.commit()
            s.close()
        except Exception as e:
            print(f"[DB] Error balance diario: {e}")