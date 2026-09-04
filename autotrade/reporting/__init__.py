"""
Reporting & Audit Logging Layer.
Calculates institutional performance metrics, generates automated daily/weekly/monthly reports,
and maintains tamper-resistant audit trails in SQLite and JSON logs.
"""

from autotrade.reporting.performance_metrics import PerformanceMetricsEngine, PortfolioMetrics
from autotrade.reporting.audit_logger import AuditLogger
from autotrade.reporting.report_generator import ReportGenerator

__all__ = [
    "PerformanceMetricsEngine",
    "PortfolioMetrics",
    "AuditLogger",
    "ReportGenerator",
]
