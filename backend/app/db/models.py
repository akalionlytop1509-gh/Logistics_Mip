from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String(50), unique=True, index=True, nullable=False)
    node_name = Column(String(200))
    node_type = Column(String(50)) # source, sink, transship, port
    tier = Column(Integer, default=0)
    design_cap = Column(Float, nullable=True)

    # Indexes
    __table_args__ = (
        Index("ix_nodes_type_tier", "node_type", "tier"),
    )

class Arc(Base):
    __tablename__ = "arcs"

    id = Column(Integer, primary_key=True, index=True)
    from_node = Column(String(50), index=True, nullable=False)
    to_node = Column(String(50), index=True, nullable=False)
    mode = Column(String(50), index=True, nullable=False)
    distance = Column(Float, default=1.0)
    capacity = Column(Float, default=1000.0)
    unit_cost = Column(Float, default=0.0)
    fixed_cost = Column(Float, default=0.0)
    is_export = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)

    # Unique/Composite Index for faster lookup and data integrity
    __table_args__ = (
        Index("uix_arc_from_to_mode", "from_node", "to_node", "mode", unique=True),
    )

class Supply(Base):
    __tablename__ = "supply"
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String(50), index=True, nullable=False)
    value = Column(Float, default=0.0)

class Demand(Base):
    __tablename__ = "demand"
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String(50), index=True, nullable=False)
    value = Column(Float, default=0.0)

class Scenario(Base):
    __tablename__ = "scenarios"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    description = Column(String(500))
    created_at = Column(String(50)) # Placeholder for DateTime
    status = Column(String(20)) # success, failed, running
