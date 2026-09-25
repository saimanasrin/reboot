"""Persistence model. Works on SQLite (default) and PostgreSQL (set QCHAIN_DATABASE_URL)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(32))
    storage_class: Mapped[str] = mapped_column(String(16))
    required_min_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_max_temperature: Mapped[float] = mapped_column(Float)
    humidity_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    declared_shelf_life_days: Mapped[float] = mapped_column(Float)
    sensitivity: Mapped[str] = mapped_column(String(16))
    min_window_days: Mapped[float] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="")
    # Full demo parameter set (clearly labelled as prototype parameters, see reference.py).
    demo_parameters: Mapped[dict] = mapped_column(JSON)


class Customer(Base):
    __tablename__ = "customers"
    customer_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(32))  # supermarket | restaurant | wholesaler | small_retailer | direct_consumer
    location_name: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    distance_km: Mapped[float] = mapped_column(Float)
    delivery_hours: Mapped[float] = mapped_column(Float)
    downstream_lag_hours: Mapped[float] = mapped_column(Float, default=0.0)
    min_receipt_days: Mapped[float] = mapped_column(Float, default=0.0)
    max_receive_kg: Mapped[float] = mapped_column(Float)
    discount_channel: Mapped[bool] = mapped_column(Boolean, default=False)
    accepts: Mapped[list] = mapped_column(JSON)
    demand_profile: Mapped[dict] = mapped_column(JSON)  # product_id -> {daily_kg, cv}
    current_inventory: Mapped[dict] = mapped_column(JSON)  # product_id -> kg on hand
    historical_demand: Mapped[dict] = mapped_column(JSON)  # product_id -> last 28 days kg


class RescuePartner(Base):
    __tablename__ = "rescue_partners"
    partner_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    location_name: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    distance_km: Mapped[float] = mapped_column(Float)
    collection_hours: Mapped[float] = mapped_column(Float)
    capacity_kg_per_day: Mapped[float] = mapped_column(Float)
    available_capacity_kg: Mapped[float] = mapped_column(Float)
    min_window_days: Mapped[float] = mapped_column(Float)
    accepts: Mapped[list] = mapped_column(JSON)
    social_value_qar_per_kg: Mapped[float] = mapped_column(Float)


class Shipment(Base):
    __tablename__ = "shipments"
    shipment_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"))
    quantity_kg: Mapped[float] = mapped_column(Float)
    production_date: Mapped[datetime] = mapped_column(DateTime)
    declared_expiry: Mapped[datetime] = mapped_column(DateTime)
    origin: Mapped[str] = mapped_column(String(120))
    transport_mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    scenario: Mapped[str] = mapped_column(String(32))
    original_customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.customer_id"), nullable=True)
    device_id: Mapped[str] = mapped_column(String(32))
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    current_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_reading_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.shipment_id"))
    device_id: Mapped[str] = mapped_column(String(32))
    ts: Mapped[datetime] = mapped_column(DateTime)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    door_open: Mapped[bool] = mapped_column(Boolean, default=False)
    motion: Mapped[str] = mapped_column(String(16), default="normal")  # stationary | normal | shock
    battery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_readings_shipment_ts", "shipment_id", "ts"),)


class JourneyEvent(Base):
    __tablename__ = "journey_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.shipment_id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(32))  # origin | transport | port | cold_storage | distribution
    segment_type: Mapped[str] = mapped_column(String(16))  # transit | handling | dwell | distribution
    label: Mapped[str] = mapped_column(String(160))
    location_name: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    start_ts: Mapped[datetime] = mapped_column(DateTime)
    end_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DemandForecast(Base):
    __tablename__ = "demand_forecasts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"))
    forecast_date: Mapped[datetime] = mapped_column(DateTime)
    expected_kg: Mapped[float] = mapped_column(Float)
    std_kg: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(64))


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.shipment_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    as_of: Mapped[datetime] = mapped_column(DateTime)
    declared_remaining_days: Mapped[float] = mapped_column(Float)
    estimated_remaining_days: Mapped[float] = mapped_column(Float)
    physics_days: Mapped[float] = mapped_column(Float)
    ml_days: Mapped[float] = mapped_column(Float)
    loss_days: Mapped[float] = mapped_column(Float)
    deterioration_score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(16))  # GOOD | MID | LOW | HOLD
    action: Mapped[str] = mapped_column(String(16))  # NORMAL | ACCELERATE | RESCUE | HOLD
    data_quality_score: Mapped[float] = mapped_column(Float)
    compliance_status: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.shipment_id"), index=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    action_label: Mapped[str] = mapped_column(String(64))
    original_waste_kg: Mapped[float] = mapped_column(Float)
    optimized_waste_kg: Mapped[float] = mapped_column(Float)
    food_saved_kg: Mapped[float] = mapped_column(Float)
    revenue_recovered_qar: Mapped[float] = mapped_column(Float)
    plan: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed | accepted
    accepted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class Simulation(Base):
    __tablename__ = "simulations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.shipment_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(64))
    options: Mapped[list] = mapped_column(JSON)


class ComplianceRule(Base):
    __tablename__ = "compliance_rules"
    rule_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    rule_type: Mapped[str] = mapped_column(String(32))  # official_threshold | prototype_policy
    applies_to: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(Text)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.shipment_id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    username: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64))
    resource: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
