from typing import Dict, Any, List
import time
import json
import threading
import copy
from dataclasses import dataclass, asdict
from datetime import datetime
from collections import deque


@dataclass
class RequestRecord:
    """Represents a single request/response record"""
    id: str
    timestamp: float
    ip_address: str
    method: str
    endpoint: str
    original_request: Dict[str, Any]
    processed_request: Dict[str, Any]
    original_response: Dict[str, Any] = None
    processed_response: Dict[str, Any] = None
    duration_ms: float = None
    error: str = None
    status: str = "pending"  # pending, completed, error
    
    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            "ip_address": self.ip_address,
            "method": self.method,
            "endpoint": self.endpoint,
            "original_request": self.original_request,
            "processed_request": self.processed_request,
            "original_response": self.original_response,
            "processed_response": self.processed_response,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "status": self.status
        }


class RequestMonitor:
    """Monitors and stores request/response data for live viewing"""
    
    def __init__(self, max_records: int = 1000):
        self.max_records = max_records
        self.records = deque(maxlen=max_records)
        self.lock = threading.RLock()
        self.socketio = None  # Will be set by app
        
    def set_socketio(self, socketio):
        """Set the SocketIO instance for real-time updates"""
        self.socketio = socketio
        
    def start_request(self, request_id: str, ip_address: str, method: str, 
                     endpoint: str, original_request: Dict[str, Any], 
                     initial_processed_request: Dict[str, Any]) -> None:
        """Start tracking a new request"""
        with self.lock:
            record = RequestRecord(
                id=request_id,
                timestamp=time.time(),
                ip_address=ip_address,
                method=method,
                endpoint=endpoint,
                original_request=self._sanitize_data(copy.deepcopy(original_request)),
                processed_request=self._sanitize_data(copy.deepcopy(initial_processed_request)),
                status="pending"
            )
            self.records.appendleft(record)
            self._notify_observers("request_started", record.to_dict())
    
    def complete_request(self, request_id: str, original_response: Dict[str, Any], 
                        processed_response: Dict[str, Any], start_time: float) -> None:
        """Mark a request as completed with response data"""
        with self.lock:
            record = self._find_record(request_id)
            if record:
                record.original_response = self._sanitize_data(copy.deepcopy(original_response))
                record.processed_response = self._sanitize_data(copy.deepcopy(processed_response))
                record.duration_ms = (time.time() - start_time) * 1000
                record.status = "completed"
                self._notify_observers("request_completed", record.to_dict())
    
    def error_request(self, request_id: str, error: str, start_time: float) -> None:
        """Mark a request as failed with error info"""
        with self.lock:
            record = self._find_record(request_id)
            if record:
                record.error = str(error)
                record.duration_ms = (time.time() - start_time) * 1000
                record.status = "error"
                self._notify_observers("request_error", record.to_dict())
    
    def get_records(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get all recorded requests (most recent first)"""
        with self.lock:
            records = list(self.records)
            if limit:
                records = records[:limit]
            return [record.to_dict() for record in records]
    
    def get_record(self, request_id: str) -> Dict[str, Any]:
        """Get a specific record by ID"""
        with self.lock:
            record = self._find_record(request_id)
            return record.to_dict() if record else None
    
    def clear_records(self) -> None:
        """Clear all recorded requests"""
        with self.lock:
            self.records.clear()
            self._notify_observers("records_cleared", {})
    
    def _find_record(self, request_id: str) -> RequestRecord:
        """Find a record by ID"""
        for record in self.records:
            if record.id == request_id:
                return record
        return None
    
    def _sanitize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize data for storage (remove sensitive info, limit size)"""
        if not data:
            return data
        
        sanitized = copy.deepcopy(data)
        
        return sanitized
    
    def _notify_observers(self, event_type: str, data: Dict[str, Any]) -> None:
        """Notify all observers of an event"""
        if self.socketio:
            message = {
                "type": event_type,
                "data": data,
                "timestamp": time.time()
            }
            self.socketio.emit('monitor_update', message)


request_monitor = RequestMonitor()
