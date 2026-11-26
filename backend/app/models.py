from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))
    team: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Batch(Base):
    """到货批次，如样例 L-7"""

    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    oem: Mapped[str] = mapped_column(String(128))
    source_vehicle: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="open")  # open|frozen|closed
    freeze_strategy: Mapped[str | None] = mapped_column(String(16), nullable=True)  # batch|single
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    packs: Mapped[list["Pack"]] = relationship(back_populates="batch")


class Pack(Base):
    """电池包：每包唯一序列号"""

    __tablename__ = "packs"

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    oem: Mapped[str] = mapped_column(String(128))
    source_vehicle: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="received", index=True)
    quarantine_slot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    responsible_team: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)  # 单包冻结标记
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    batch: Mapped["Batch"] = relationship(back_populates="packs")
    transport_events: Mapped[list["TransportEvent"]] = relationship(
        back_populates="pack", cascade="all, delete-orphan"
    )
    modules: Mapped[list["Module"]] = relationship(back_populates="pack")


class TransportEvent(Base):
    """运输中的碰撞 / 浸水 / 热事件记录（不可被 BMS 正常读数抵消）"""

    __tablename__ = "transport_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id"))
    event_type: Mapped[str] = mapped_column(String(16))  # collision|water|thermal
    description: Mapped[str] = mapped_column(Text, default="")
    source_doc: Mapped[str] = mapped_column(String(128), default="")  # 回执编号
    case_closed: Mapped[bool] = mapped_column(Boolean, default=False)  # 热事件结案标记
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pack: Mapped["Pack"] = relationship(back_populates="transport_events")


class Receipt(Base):
    """收货单：重复扫码只返回原单"""

    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id"), unique=True)
    receiver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    scan_payload: Mapped[str] = mapped_column(Text)
    quarantine_slot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    responsible_team: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuarantineRecord(Base):
    """隔离记录：区分整批隔离与单包隔离"""

    __tablename__ = "quarantine_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    pack_id: Mapped[int | None] = mapped_column(ForeignKey("packs.id"), nullable=True)
    scope: Mapped[str] = mapped_column(String(16))  # batch|single
    reason: Mapped[str] = mapped_column(Text)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    released: Mapped[bool] = mapped_column(Boolean, default=False)
    release_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkOrder(Base):
    """拆解工单"""

    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id"))
    status: Mapped[str] = mapped_column(String(32), default="created")
    # created|in_progress|pending_verification|completed
    witness1_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    witness2_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    witnessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Module(Base):
    """模组：父子关系指向来源包；无法确认父子关系时隔离待核"""

    __tablename__ = "modules"
    __table_args__ = (UniqueConstraint("serial_no", name="uq_module_serial"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_no: Mapped[str] = mapped_column(String(64), index=True)
    pack_id: Mapped[int | None] = mapped_column(ForeignKey("packs.id"), nullable=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="linked")
    # linked|quarantine_review|reusable|pending_recycle|outbound|rejected_returned
    unknown_parent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pack: Mapped["Pack | None"] = relationship(back_populates="modules")


class LabelHistory(Base):
    """重贴标签：保留旧号、操作者与时间，换标需两人分别确认"""

    __tablename__ = "label_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(16))  # pack|module
    entity_id: Mapped[int] = mapped_column(Integer)
    old_serial: Mapped[str] = mapped_column(String(64))
    new_serial: Mapped[str] = mapped_column(String(64))
    operator1_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    operator2_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Device(Base):
    """检测设备：含校准有效期"""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_no: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    calibrated_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InspectionRecord(Base):
    """检测台回执：绝缘测试、BMS 读数、复检结论"""

    __tablename__ = "inspection_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    is_reinspection: Mapped[bool] = mapped_column(Boolean, default=False)
    insulation_pass: Mapped[bool] = mapped_column(Boolean)
    bms_reading_ok: Mapped[bool] = mapped_column(Boolean)
    result: Mapped[str] = mapped_column(String(16))  # pass|fail|pending
    inspector_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    """安全放行单（带版本；退回补检后旧单 voided，拣货单与买家通知同步更正）"""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    decision: Mapped[str] = mapped_column(String(16))  # echelon|recycle|reinspect
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|voided|superseded
    purpose: Mapped[str | None] = mapped_column(String(128), nullable=True)       # 用途
    consignee: Mapped[str | None] = mapped_column(String(128), nullable=True)     # 收货人
    quantity_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)    # 限数量
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rationale: Mapped[str] = mapped_column(Text, default="")
    voided_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PickingOrder(Base):
    """仓库拣货单：只能按已批准去向拣货"""

    __tablename__ = "picking_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    approval_id: Mapped[int] = mapped_column(ForeignKey("approvals.id"))
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id"))
    status: Mapped[str] = mapped_column(String(16), default="waiting")
    # waiting|corrected|picked|cancelled
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    correction_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    picked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboundOrder(Base):
    """出库单：限数量、用途、收货人；装车后不可删除，只能召回/退运"""

    __tablename__ = "outbound_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    approval_id: Mapped[int] = mapped_column(ForeignKey("approvals.id"))
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(128))
    consignee: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="created")
    # created|notified|shipped|rejected|recalled|returned|signed
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BuyerNotification(Base):
    """下游买家通知；放行单失效时发送更正通知"""

    __tablename__ = "buyer_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    outbound_order_id: Mapped[int] = mapped_column(ForeignKey("outbound_orders.id"))
    consignee: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SignOff(Base):
    """下游签收端：签收或拒收（拒收只能退回隔离待复核）"""

    __tablename__ = "sign_offs"

    id: Mapped[int] = mapped_column(primary_key=True)
    outbound_order_id: Mapped[int] = mapped_column(ForeignKey("outbound_orders.id"))
    action: Mapped[str] = mapped_column(String(16))  # signed|rejected
    signer: Mapped[str] = mapped_column(String(128))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecycleWeighing(Base):
    """回收称重记录"""

    __tablename__ = "recycle_weighings"

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int | None] = mapped_column(ForeignKey("modules.id"), nullable=True)
    pack_id: Mapped[int | None] = mapped_column(ForeignKey("packs.id"), nullable=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Reconciliation(Base):
    """批次数量核对：差额未解释前阻止批次结清"""

    __tablename__ = "reconciliations"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    dismantled_qty: Mapped[int] = mapped_column(Integer, default=0)   # 实际拆出数量
    released_qty: Mapped[int] = mapped_column(Integer, default=0)      # 放行数量
    shipped_qty: Mapped[int] = mapped_column(Integer, default=0)       # 已发数量
    recycled_weight_kg: Mapped[float] = mapped_column(Float, default=0.0)
    difference: Mapped[int] = mapped_column(Integer, default=0)
    explained: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecallOrder(Base):
    """召回 / 退运：装车货物不能删除，只能走召回或退运"""

    __tablename__ = "recall_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    outbound_order_id: Mapped[int] = mapped_column(ForeignKey("outbound_orders.id"))
    kind: Mapped[str] = mapped_column(String(16))  # recall|return
    reason: Mapped[str] = mapped_column(Text)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """全链路审计日志"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
