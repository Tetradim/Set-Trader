"""SLO (Service Level Objective) and Alerting Configuration.

Defines SLOs, error budgets, and alerting policies.
"""
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from enum import Enum


logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class SLO:
    """Service Level Objective."""
    name: str
    description: str
    metric: str
    target: float  # e.g., 99.9 for 99.9%
    window: str  # rolling window: 1h, 24h, 7d, 30d
    
    # Calculated fields
    error_budget_remaining: float = 100.0
    error_budget_used: float = 0.0
    current_value: float = 100.0
    is_burned: bool = False
    last_updated: datetime = None


@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    description: str
    severity: AlertSeverity
    condition: str  # e.g., "error_rate > 0.01"
    threshold: float
    evaluation_window: str = "5m"
    notification_channels: List[str] = field(default_factory=list)
    is_enabled: bool = True
    
    # Runbook reference
    runbook_id: Optional[str] = None


@dataclass
class Incident:
    """Alert incident."""
    incident_id: str
    alert_rule: str
    severity: AlertSeverity
    title: str
    description: str
    status: str = "triggered"  # triggered, acknowledged, resolved
    created_at: datetime = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


# Default SLOs
DEFAULT_SLOS = [
    SLO(
        name="api_availability",
        description="API server availability",
        metric="http_requests_success_total / http_requests_total",
        target=99.9,
        window="24h"
    ),
    SLO(
        name="api_latency_p95",
        description="API latency P95",
        metric="http_request_duration_seconds_p95",
        target=95.0,  # Target: 95% of requests under 500ms
        window="24h"
    ),
    SLO(
        name="order_execution_success",
        description="Order execution success rate",
        metric="orders_filled_total / orders_submitted_total",
        target=99.5,
        window="24h"
    ),
    SLO(
        name="websocket_connectivity",
        description="WebSocket connection stability",
        metric="ws_messages_sent_total / ws_connections_total",
        target=99.9,
        window="24h"
    ),
    SLO(
        name="price_feed_latency",
        description="Price feed latency",
        metric="price_update_latency_seconds_p99",
        target=99.0,
        window="1h"
    ),
]

# Default Alert Rules
DEFAULT_ALERTS = [
    AlertRule(
        name="api_down",
        description="API server is not responding",
        severity=AlertSeverity.CRITICAL,
        condition="api_availability < 0.95",
        threshold=0.95,
        notification_channels=["pagerduty", "slack"],
        runbook_id="RB001"
    ),
    AlertRule(
        name="high_error_rate",
        description="High error rate detected",
        severity=AlertSeverity.WARNING,
        condition="error_rate > 0.01",
        threshold=0.01,
        notification_channels=["slack"],
        runbook_id="RB002"
    ),
    AlertRule(
        name="high_latency",
        description="API latency above threshold",
        severity=AlertSeverity.WARNING,
        condition="http_request_duration_seconds_p95 > 0.5",
        threshold=0.5,
        notification_channels=["slack"],
        runbook_id="RB003"
    ),
    AlertRule(
        name="order_execution_failure",
        description="Order execution failure rate above threshold",
        severity=AlertSeverity.CRITICAL,
        condition="order_failure_rate > 0.05",
        threshold=0.05,
        notification_channels=["pagerduty", "slack", "telegram"],
        runbook_id="RB004"
    ),
    AlertRule(
        name="price_feed_stale",
        description="Price feed not updating",
        severity=AlertSeverity.WARNING,
        condition="price_feed_staleness_seconds > 60",
        threshold=60,
        runbook_id="RB005"
    ),
    AlertRule(
        name="broker_disconnected",
        description="Broker connection lost",
        severity=AlertSeverity.CRITICAL,
        condition="broker_connected == false",
        threshold=0,
        notification_channels=["pagerduty", "slack", "telegram"],
        runbook_id="RB001"
    ),
]


class SLOTracker:
    """Tracks SLOs and calculates error budgets."""
    
    def __init__(self):
        self.slos: Dict[str, SLO] = {}
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_incidents: List[Incident] = []
        
        # Initialize default SLOs and alerts
        for slo in DEFAULT_SLOS:
            self.slos[slo.name] = slo
        for alert in DEFAULT_ALERTS:
            self.alert_rules[alert.name] = alert
    
    def update_slo(self, name: str, value: float):
        """Update SLO metric value."""
        if name not in self.slos:
            logger.warning(f"SLO {name} not found")
            return
        
        slo = self.slos[name]
        slo.current_value = value
        slo.last_updated = datetime.utcnow()
        
        # Calculate error budget
        slo.error_budget_remaining = slo.target - (100 - value)
        slo.error_budget_used = 100 - value - (100 - slo.target)
        slo.is_burned = slo.error_budget_remaining < 0
    
    def get_slo_status(self, name: str) -> Optional[SLO]:
        """Get SLO status."""
        return self.slos.get(name)
    
    def get_all_slos(self) -> List[SLO]:
        """Get all SLOs."""
        return list(self.slos.values())
    
    def evaluate_alerts(self, metrics: Dict[str, float]) -> List[AlertRule]:
        """Evaluate alert rules against current metrics."""
        triggered = []
        
        for name, alert in self.alert_rules.items():
            if not alert.is_enabled:
                continue
            
            # Get metric value
            metric_value = metrics.get(alert.condition.split()[0], 0)
            operator = alert.condition.split()[1]
            threshold = alert.threshold
            
            # Evaluate condition
            is_triggered = False
            if operator == ">" and metric_value > threshold:
                is_triggered = True
            elif operator == "<" and metric_value < threshold:
                is_triggered = True
            elif operator == "==" and metric_value == threshold:
                is_triggered = True
            
            if is_triggered:
                triggered.append(alert)
        
        return triggered
    
    def create_incident(self, alert_rule: str, title: str, description: str) -> Incident:
        """Create a new incident."""
        incident = Incident(
            incident_id=f"INC{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            alert_rule=alert_rule,
            severity=self.alert_rules[alert_rule].severity,
            title=title,
            description=description,
            created_at=datetime.utcnow()
        )
        self.active_incidents.append(incident)
        logger.warning(f"Incident created: {incident.incident_id} - {title}")
        return incident
    
    def acknowledge_incident(self, incident_id: str, user: str) -> bool:
        """Acknowledge an incident."""
        for inc in self.active_incidents:
            if inc.incident_id == incident_id and inc.status == "triggered":
                inc.status = "acknowledged"
                inc.acknowledged_at = datetime.utcnow()
                inc.acknowledged_by = user
                return True
        return False
    
    def resolve_incident(self, incident_id: str, user: str) -> bool:
        """Resolve an incident."""
        for inc in self.active_incidents:
            if inc.incident_id == incident_id:
                inc.status = "resolved"
                inc.resolved_at = datetime.utcnow()
                inc.resolved_by = user
                return True
        return False
    
    def get_active_incidents(self) -> List[Incident]:
        """Get all active incidents."""
        return [i for i in self.active_incidents if i.status != "resolved"]


# Global tracker
_slo_tracker = SLOTracker()


def get_slo_tracker() -> SLOTracker:
    """Get the global SLO tracker."""
    return _slo_tracker


def get_slos() -> List[Dict]:
    """Get all SLOs as dictionaries."""
    tracker = get_slo_tracker()
    return [
        {
            "name": slo.name,
            "description": slo.description,
            "target": slo.target,
            "window": slo.window,
            "current_value": slo.current_value,
            "error_budget_remaining": slo.error_budget_remaining,
            "is_burned": slo.is_burned,
            "last_updated": slo.last_updated.isoformat() if slo.last_updated else None
        }
        for slo in tracker.get_all_slos()
    ]


def get_alerts() -> List[Dict]:
    """Get all alert rules."""
    tracker = get_slo_tracker()
    return [
        {
            "name": alert.name,
            "description": alert.description,
            "severity": alert.severity.value,
            "condition": alert.condition,
            "threshold": alert.threshold,
            "is_enabled": alert.is_enabled,
            "runbook_id": alert.runbook_id
        }
        for alert in tracker.alert_rules.values()
    ]


def get_incidents() -> List[Dict]:
    """Get all incidents."""
    tracker = get_slo_tracker()
    return [
        {
            "incident_id": inc.incident_id,
            "alert_rule": inc.alert_rule,
            "severity": inc.severity.value,
            "title": inc.title,
            "description": inc.description,
            "status": inc.status,
            "created_at": inc.created_at.isoformat() if inc.created_at else None
        }
        for inc in tracker.get_active_incidents()
    ]


__all__ = [
    "AlertSeverity",
    "SLO",
    "AlertRule", 
    "Incident",
    "SLOTracker",
    "get_slo_tracker",
    "get_slos",
    "get_alerts",
    "get_incidents",
]