import os
import sys
sys.path.insert(0, '.')

from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config.settings import DB_PATH

Base = declarative_base()


class Trade(Base):
    __tablename__ = "trades"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    orden_id       = Column(String, unique=True)
    par            = Column(String)
    lado           = Column(String)
    precio_entrada = Column(Float)
    precio_salida  = Column(Float, nullable=True)
    cantidad_usdt  = Column(Float)
    pnl_usdt       = Column(Float, nullable=True)
    pnl_pct        = Column(Float, nullable=True)
    stop_loss      = Column(Float)
    take_profit    = Column(Float)
    confianza      = Column(Integer)
    razon_entrada  = Column(String)
    razon_salida   = Column(String, nullable=True)
    rsi_entrada    = Column(Float, nullable=True)
    tendencia      = Column(String, nullable=True)
    ganado         = Column(Boolean, nullable=True)
    abierta_en     = Column(DateTime, default=datetime.now)
    cerrada_en     = Column(DateTime, nullable=True)
    duracion_min   = Column(Integer, nullable=True)


class BalanceDiario(Base):
    __tablename__ = "balance_diario"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    fecha      = Column(DateTime, default=datetime.now)
    balance    = Column(Float)
    pnl_dia    = Column(Float)
    trades_dia = Column(Integer)
    ganados    = Column(Integer)
    perdidos   = Column(Integer)


class Database:

    def __init__(self):
        # Crear carpeta data si no existe
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.engine  = create_engine(f"sqlite:///{DB_PATH}", echo=False)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        print("[OK] Base de datos iniciada")

    def guardar_trade_abierto(self, op):
        try:
            trade = Trade(
                orden_id       = op["orden_id"],
                par            = op["par"],
                lado           = op["lado"],
                precio_entrada = op["precio_entrada"],
                cantidad_usdt  = op["tamaño_usdt"],
                stop_loss      = op["stop_loss"],
                take_profit    = op["take_profit"],
                confianza      = op.get("confianza", 0),
                razon_entrada  = op.get("razon", ""),
                rsi_entrada    = op.get("rsi", None),
                tendencia      = op.get("tendencia", None),
                abierta_en     = op.get("abierta_en", datetime.now()),
            )
            self.session.add(trade)
            self.session.commit()
            print(f"[DB] Trade guardado: {op['par']} {op['lado']}")
        except Exception as e:
            print(f"[DB ERROR] {e}")
            self.session.rollback()

    def cerrar_trade(self, orden_id, precio_salida, pnl_usdt, razon_salida):
        try:
            trade = self.session.query(Trade).filter_by(orden_id=orden_id).first()
            if trade:
                ahora = datetime.now()
                trade.precio_salida = precio_salida
                trade.pnl_usdt      = pnl_usdt
                trade.pnl_pct       = (pnl_usdt / trade.cantidad_usdt) * 100
                trade.razon_salida  = razon_salida
                trade.ganado        = pnl_usdt >= 0
                trade.cerrada_en    = ahora
                trade.duracion_min  = int((ahora - trade.abierta_en).total_seconds() / 60)
                self.session.commit()
                print(f"[DB] Trade cerrado: {trade.par} | PnL: {pnl_usdt:.2f}")
        except Exception as e:
            print(f"[DB ERROR] {e}")
            self.session.rollback()

    def guardar_balance_diario(self, balance, pnl_dia, trades_dia, ganados, perdidos):
        try:
            registro = BalanceDiario(
                balance    = balance,
                pnl_dia    = pnl_dia,
                trades_dia = trades_dia,
                ganados    = ganados,
                perdidos   = perdidos,
            )
            self.session.add(registro)
            self.session.commit()
            print(f"[DB] Balance diario guardado: ${balance:.2f}")
        except Exception as e:
            print(f"[DB ERROR] {e}")
            self.session.rollback()

    def get_trades_historial(self, limite=50):
        try:
            return self.session.query(Trade)\
                .filter(Trade.cerrada_en != None)\
                .order_by(Trade.cerrada_en.desc())\
                .limit(limite).all()
        except Exception:
            return []

    def get_trades_abiertos(self):
        try:
            return self.session.query(Trade)\
                .filter(Trade.cerrada_en == None).all()
        except Exception:
            return []

    def get_estadisticas(self):
        try:
            todos    = self.session.query(Trade).filter(Trade.cerrada_en != None).all()
            ganados  = [t for t in todos if t.ganado]
            perdidos = [t for t in todos if not t.ganado]
            pnl_total = sum(t.pnl_usdt for t in todos if t.pnl_usdt)
            mejor = max(todos, key=lambda t: t.pnl_usdt or 0, default=None)
            peor  = min(todos, key=lambda t: t.pnl_usdt or 0, default=None)
            winrate = 0
            if todos:
                winrate = int((len(ganados) / len(todos)) * 100)
            return {
                "total_trades": len(todos),
                "ganados":      len(ganados),
                "perdidos":     len(perdidos),
                "winrate":      winrate,
                "pnl_total":    round(pnl_total, 2),
                "mejor_trade":  round(mejor.pnl_usdt, 2) if mejor else 0,
                "peor_trade":   round(peor.pnl_usdt, 2) if peor else 0,
            }
        except Exception:
            return {}

    def get_balance_historico(self, dias=30):
        try:
            registros = self.session.query(BalanceDiario)\
                .order_by(BalanceDiario.fecha.desc())\
                .limit(dias).all()
            return list(reversed(registros))
        except Exception:
            return []