#!/usr/bin/env python3
"""
Error Collection Module for OpenStack Pod Logs

Extracts and deduplicates ERROR/CRITICAL blocks from OpenStack service pods
during test execution.
"""

import logging
import re
import subprocess
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class ErrorCollector:
    """
    Collects and analyzes error logs from OpenStack service pods.
    Uses fuzzy matching to deduplicate similar error messages.
    """
    
    def __init__(self, namespace: str = "openstack"):
        """
        Initialize the error collector.
        
        Args:
            namespace: Kubernetes namespace to monitor
        """
        self.namespace = namespace
        
        # Pod patterns to monitor for errors
        # Includes both OpenStack service pods AND Tempest test pods
        self.openstack_pod_patterns = [
            'octavia-api', 'octavia-worker', 'octavia-housekeeping', 'octavia-health-manager',
            'designate-api', 'designate-central', 'designate-worker', 'designate-producer',
            'designate-mdns', 'designate-sink',
            'neutron-api', 'neutron-dhcp-agent', 'neutron-l3-agent', 'neutron-metadata-agent',
            'neutron-ovn-metadata-agent', 'neutron-sriov-agent',
            'nova-api', 'nova-conductor', 'nova-scheduler', 'nova-compute',
            'cinder-api', 'cinder-scheduler', 'cinder-volume', 'cinder-backup',
            'glance-api',
            'keystone-api',
            'placement-api',
            'heat-api', 'heat-engine',
            'manila-api', 'manila-scheduler', 'manila-share',
            'barbican-api', 'barbican-worker',
            'horizon'
        ]
        
        # Tempest test pod patterns
        self.test_pod_patterns = [
            'tempest-',  # All pods starting with 'tempest-'
        ]
        
        # Similarity threshold for fuzzy matching (0-100)
        self.similarity_threshold = 85
        
        # Number of context lines to capture before and after an error (for debugging context)
        self.context_lines_before = 5
        self.context_lines_after = 5
    
    def detect_openstack_pods(self) -> List[Dict]:
        """
        Detect all running OpenStack service pods and Tempest test pods.
        
        Returns:
            List of dictionaries with pod info: {'name': str, 'service': str, 'type': str}
        """
        try:
            cmd = [
                'oc', 'get', 'pods',
                '-n', self.namespace,
                '-o', 'json'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"Failed to get pods: {result.stderr}")
                return []
            
            import json
            pods_data = json.loads(result.stdout)
            
            detected_pods = []
            for pod in pods_data.get('items', []):
                pod_name = pod['metadata']['name']
                phase = pod['status'].get('phase', '')
                
                # Check if pod is running (or completed/succeeded for test pods)
                # Test pods may be in 'Succeeded' state but we still want their logs
                if phase not in ['Running', 'Succeeded', 'Failed']:
                    continue
                
                # Check OpenStack service pods
                matched = False
                for pattern in self.openstack_pod_patterns:
                    if pattern in pod_name:
                        # Extract service name (e.g., 'octavia' from 'octavia-api-xyz')
                        service = pattern.split('-')[0]
                        detected_pods.append({
                            'name': pod_name,
                            'service': service,
                            'type': 'openstack'
                        })
                        matched = True
                        break
                
                # Check test pods if not already matched
                if not matched:
                    for pattern in self.test_pod_patterns:
                        if pod_name.startswith(pattern):
                            # Extract service from test pod name (e.g., 'tempest-octavia' -> 'octavia')
                            # Test pod format: tempest-<service>-<test-name>-<hash>
                            parts = pod_name.split('-')
                            if len(parts) >= 2:
                                service = parts[1] if len(parts) > 1 else 'tempest'
                            else:
                                service = 'tempest'
                            
                            detected_pods.append({
                                'name': pod_name,
                                'service': service,
                                'type': 'test'
                            })
                            break
            
            if detected_pods:
                openstack_count = sum(1 for p in detected_pods if p.get('type') == 'openstack')
                test_count = sum(1 for p in detected_pods if p.get('type') == 'test')
                
                logger.info(f"Detected {len(detected_pods)} pods for error collection:")
                logger.info(f"  - {openstack_count} OpenStack service pods")
                logger.info(f"  - {test_count} Tempest test pods")
                
                # Log unique services
                services = sorted(set(p['service'] for p in detected_pods))
                logger.info(f"Services: {', '.join(services)}")
            
            return detected_pods
            
        except Exception as e:
            logger.error(f"Error detecting pods: {e}")
            return []
    
    def _is_error_or_critical_log_level(self, line: str) -> bool:
        """
        Check if a log line has ERROR or CRITICAL as the actual log level.
        Does NOT match if ERROR/CRITICAL appears in the message content.
        
        OpenStack log format:
        2025-11-17 11:19:19.758 15 DEBUG designate.central.service [...] message
                                   ^^^^^
                                   This is the log level field!
        
        Common formats:
        - "YYYY-MM-DD HH:MM:SS.mmm PID LEVEL module [context] message"
        - "YYYY-MM-DDTHH:MM:SS.mmm PID LEVEL module [context] message"
        
        Args:
            line: Log line to check
            
        Returns:
            True if the log level field is ERROR or CRITICAL, False otherwise
            
        Examples:
            ✅ "2025-11-17 11:19:19.758 15 ERROR designate.api ..." → True
            ✅ "2025-11-17 11:19:19.758 15 CRITICAL nova.compute ..." → True
            ❌ "2025-11-17 11:19:19.758 15 DEBUG designate.api [...] status ERROR" → False
            ❌ "2025-11-17 11:19:19.758 15 INFO neutron.agent [...] ERROR in data" → False
        """
        # Match OpenStack log format: timestamp + PID + log_level + module
        # Look for ERROR or CRITICAL in the log level field (after timestamp/PID, before module name)
        pattern = r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]\d+\s+\d+\s+(ERROR|CRITICAL)\s+'
        return re.search(pattern, line, re.IGNORECASE) is not None
    
    def _has_error_keywords_in_prefix(self, line: str) -> bool:
        """
        Check if error-related keywords appear in the first 50 characters of a line.
        
        This is a FLEXIBLE detection method for logs that don't follow standard format.
        Useful for:
        - Test pod output (non-standard format)
        - Different log formats from various services
        - Tracebacks without standard timestamp prefix
        - Connectivity/network issues
        - System crashes and resource exhaustion
        - Python/Java exception messages
        
        Keywords checked (50+ keywords across categories):
        - Error levels: ERROR, CRITICAL, FATAL, PANIC, FAIL, FAILED
        - Exceptions: EXCEPTION, TRACEBACK, RAISE, THROWN, *Error (Python/Java)
        - Connectivity: TIMEOUT, REFUSED, UNREACHABLE, DISCONNECT, CONNECTION
        - System: CRASH, HUNG, DEADLOCK, SEGFAULT, OOM, OUT OF MEMORY
        - Access: DENIED, FORBIDDEN, UNAUTHORIZED, PERMISSION
        - HTTP: HTTP 4XX/5XX, STATUS 4XX/5XX, 500, 502, 503, 504
        - Database: ROLLBACK, CONSTRAINT, INTEGRITY
        - Validation: INVALID, MALFORMED, UNEXPECTED
        
        Args:
            line: Log line to check
            
        Returns:
            True if error keywords found in first 50 chars, False otherwise
            
        Examples:
            ✅ "{1} test.name [0.736s] ... FAILED" → True
            ✅ "Traceback (most recent call last):" → True
            ✅ "ERROR: Connection refused" → True
            ✅ "CRITICAL: Database unavailable" → True
            ✅ "Exception occurred while processing" → True
            ✅ "Connection timeout after 30 seconds" → True
            ✅ "KeyError: 'missing_key' not found" → True
            ✅ "NullPointerException at line 42" → True
            ✅ "Service unavailable (503)" → True
            ❌ "This is a normal log line mentioning error later in the message..." → False
        """
        # Check first 50 characters only
        prefix = line[:50].upper()
        
        # Comprehensive list of error keywords to detect potential problems
        error_keywords = [
            # Basic error levels
            'ERROR', 'CRITICAL', 'FATAL', 'PANIC', 'FAIL', 'FAILED',
            
            # Exception indicators
            'EXCEPTION', 'TRACEBACK', 'RAISE', 'THROWN',
            
            # Connectivity/Network issues
            'TIMEOUT', 'TIMED OUT', 'REFUSED', 'UNREACHABLE', 'DISCONNECT',
            'CONNECTION', 'CLOSED', 'BROKEN PIPE', 'RESET', 'ABORT',
            
            # Python exceptions (common ones)
            'KEYERROR', 'VALUEERROR', 'ATTRIBUTEERROR', 'TYPEERROR',
            'INDEXERROR', 'IMPORTERROR', 'RUNTIMEERROR', 'MEMORYERROR',
            'OSERROR', 'IOERROR', 'ASSERTIONERROR',
            
            # Java exceptions (common ones)
            'NULLPOINTEREXCEPTION', 'OUTOFMEMORYERROR', 'STACKOVERFLOWERROR',
            'ILLEGALARGUMENTEXCEPTION', 'CLASSNOTFOUNDEXCEPTION',
            
            # System/Resource issues
            'CRASH', 'HUNG', 'DEADLOCK', 'CORRUPT', 'SEGFAULT',
            'CORE DUMP', 'OOM', 'OUT OF MEMORY',
            
            # Access/Permission issues
            'DENIED', 'FORBIDDEN', 'UNAUTHORIZED', 'PERMISSION',
            
            # Availability issues
            'UNAVAILABLE', 'DOWN', 'OFFLINE', 'UNREACHABLE',
            
            # Database issues
            'ROLLBACK', 'CONSTRAINT', 'INTEGRITY',
            
            # Validation issues
            'INVALID', 'MALFORMED', 'UNEXPECTED',
            
            # HTTP error codes (in text form for logs)
            'HTTP 4', 'HTTP 5', 'STATUS 4', 'STATUS 5',
            '500 ', '502 ', '503 ', '504 ',
        ]
        
        return any(keyword in prefix for keyword in error_keywords)
    
    def _normalize_error_text(self, text: str) -> str:
        """
        Normalize error text for fuzzy matching by removing dynamic content.
        
        Removes:
        - Timestamps
        - UUIDs
        - Request IDs
        - IP addresses
        - Numeric IDs
        
        Args:
            text: Original error text
        
        Returns:
            Normalized text for comparison
        """
        # Remove timestamps (various formats)
        text = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)?', '<TIMESTAMP>', text)
        text = re.sub(r'\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}', '<TIMESTAMP>', text)
        
        # Remove UUIDs
        text = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<UUID>', text, flags=re.IGNORECASE)
        
        # Remove request IDs (req-xxx)
        text = re.sub(r'req-[0-9a-f-]+', '<REQ-ID>', text, flags=re.IGNORECASE)
        
        # Remove IP addresses
        text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?\b', '<IP>', text)
        
        # Remove numeric IDs (but keep error codes)
        text = re.sub(r'\bid[:=]\s*\d+\b', 'id=<ID>', text, flags=re.IGNORECASE)
        
        # Remove memory addresses
        text = re.sub(r'0x[0-9a-fA-F]+', '<ADDR>', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two error texts using SequenceMatcher.
        
        Args:
            text1: First error text (normalized)
            text2: Second error text (normalized)
        
        Returns:
            Similarity score (0-100)
        """
        return SequenceMatcher(None, text1, text2).ratio() * 100
    
    def _extract_context_before(self, lines: List[str], error_line_index: int) -> List[str]:
        """
        Extract context lines before an error for debugging.
        
        Captures up to N lines before the error, but stops at:
        - Previous ERROR/CRITICAL line (don't mix errors)
        - Empty line followed by a gap (log block separator)
        - Beginning of log
        
        Args:
            lines: All log lines
            error_line_index: Index of the error line
        
        Returns:
            List of context lines (may be empty)
        """
        context = []
        start_index = max(0, error_line_index - self.context_lines_before)
        
        for idx in range(error_line_index - 1, start_index - 1, -1):
            if idx < 0:
                break
            
            line = lines[idx]
            
            # Stop if we hit another ERROR/CRITICAL (don't mix errors)
            if re.search(r'\b(ERROR|CRITICAL)\b', line, re.IGNORECASE):
                # Check if it's a real error line (not just a string containing "error")
                if re.search(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}.*?(ERROR|CRITICAL)', line, re.IGNORECASE):
                    break
            
            # Stop at empty lines followed by another empty line (log block separator)
            if not line.strip():
                if idx > 0 and not lines[idx - 1].strip():
                    break
            
            context.insert(0, line)
        
        # Add a separator comment to distinguish context from actual error
        if context:
            context.append("--- [Context: 5 lines before error] ---")
        
        return context
    
    def _extract_context_after(self, lines: List[str], error_end_index: int) -> List[str]:
        """
        Extract context lines after an error for debugging.
        
        Captures up to N lines after the error, but stops at:
        - Next ERROR/CRITICAL line (don't mix errors)
        - Empty line followed by a gap (log block separator)
        - End of log
        
        Args:
            lines: All log lines
            error_end_index: Index of the last line of the error block
        
        Returns:
            List of context lines (may be empty)
        """
        context = []
        end_index = min(len(lines), error_end_index + self.context_lines_after + 1)
        
        for idx in range(error_end_index + 1, end_index):
            if idx >= len(lines):
                break
            
            line = lines[idx]
            
            # Stop if we hit another ERROR/CRITICAL (don't mix errors)
            if re.search(r'\b(ERROR|CRITICAL)\b', line, re.IGNORECASE):
                # Check if it's a real error line (not just a string containing "error")
                if re.search(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}.*?(ERROR|CRITICAL)', line, re.IGNORECASE):
                    break
            
            # Stop at empty lines followed by another empty line (log block separator)
            if not line.strip():
                if idx + 1 < len(lines) and not lines[idx + 1].strip():
                    break
            
            context.append(line)
        
        # Add a separator comment to distinguish context from error
        if context:
            context.insert(0, "--- [Context: 5 lines after error] ---")
        
        return context
    
    def _extract_error_blocks(self, log_text: str, pod_name: str, service: str, pod_type: str = 'openstack') -> List[Dict]:
        """
        Extract complete error blocks from log text, including full Python tracebacks.
        
        OpenStack logs often have this format where EVERY line is prefixed with ERROR:
        2025-11-16 14:24:36.475 17 ERROR designate.module Traceback (most recent call last):
        2025-11-16 14:24:36.475 17 ERROR designate.module   File "...", line X, in func
        2025-11-16 14:24:36.475 17 ERROR designate.module     code
        2025-11-16 14:24:36.475 17 ERROR designate.module ExceptionType: message
        
        This method captures the ENTIRE traceback block as ONE error.
        
        Args:
            log_text: Raw log text
            pod_name: Name of the pod
            service: Service name
            pod_type: Type of pod ('openstack' or 'test')
        
        Returns:
            List of error dictionaries with complete traceback blocks
        """
        errors = []
        lines = log_text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Look for lines that contain "Traceback (most recent call last)" - this is the START of an error block
            # OR lines with ERROR/CRITICAL log level that are NOT part of a traceback (standalone errors)
            # Use BOTH strict (structured log) AND flexible (keyword in prefix) detection
            if 'Traceback (most recent call last)' in line and (
                self._is_error_or_critical_log_level(line) or 
                self._has_error_keywords_in_prefix(line)
            ):
                # Found the start of a traceback
                # Start error block with the traceback line
                error_block = [line]
                
                # Extract timestamp and base pattern from first line
                timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})', line)
                timestamp = timestamp_match.group(1) if timestamp_match else None
                severity = 'CRITICAL' if 'CRITICAL' in line.upper() else 'ERROR'
                
                # Extract the module prefix pattern (e.g., "ERROR designate.objects.adapters.base")
                # to identify continuation lines
                prefix_match = re.search(r'(ERROR|CRITICAL)\s+[\w\.]+', line, re.IGNORECASE)
                module_prefix = prefix_match.group(0) if prefix_match else None
                
                # Capture all subsequent lines that are part of this traceback
                j = i + 1
                max_lines = 200
                
                while j < len(lines) and j < i + max_lines:
                    next_line = lines[j]
                    
                    # If empty line, check if next line is a new log entry
                    if not next_line.strip():
                        if j + 1 < len(lines):
                            peek_line = lines[j + 1]
                            # If next line is a new timestamp + different pattern, stop
                            if re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', peek_line):
                                # Check if it's the same module continuing or a new entry
                                if module_prefix and module_prefix not in peek_line:
                                    break
                        j += 1
                        continue
                    
                    # Check if this line is part of the same error block
                    # Same module prefix OR continuation line (starts with same timestamp + module)
                    is_continuation = False
                    
                    if timestamp and timestamp in next_line:
                        # Same timestamp - likely same error
                        if module_prefix and module_prefix in next_line:
                            is_continuation = True
                        # Also capture lines with same timestamp but different format (e.g., HTTP logs after error)
                        elif not re.search(r'(INFO|DEBUG|WARNING)\s', next_line, re.IGNORECASE):
                            is_continuation = True
                    elif next_line.startswith('    ') or next_line.startswith('\t'):
                        # Indented line (traceback continuation)
                        is_continuation = True
                    elif re.match(r'^\s+File\s+"', next_line):
                        # Stack frame line
                        is_continuation = True
                    
                    if is_continuation:
                        error_block.append(next_line)
                        j += 1
                    else:
                        # Check if this is a new log entry (different timestamp + module)
                        if re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', next_line):
                            # New log entry - stop here
                            break
                        else:
                            # Might be continuation without timestamp
                            error_block.append(next_line)
                            j += 1
                
                error_text = '\n'.join(error_block)
                
                if len(error_block) > 0:
                    errors.append({
                        'pod_name': pod_name,
                        'service': service,
                        'pod_type': pod_type,
                        'timestamp': timestamp,
                        'severity': severity,
                        'error_text': error_text,
                        'normalized_text': self._normalize_error_text(error_text),
                        'has_traceback': True
                    })
                    
                    logger.debug(f"Extracted {len(error_block)}-line traceback block from {pod_name}")
                
                # Skip all processed lines
                i = j
                
            elif self._is_error_or_critical_log_level(line) or self._has_error_keywords_in_prefix(line):
                # This is an ERROR/CRITICAL line detected by:
                #   1. Strict method: actual ERROR/CRITICAL log level in structured log
                #   2. Flexible method: error keywords in first 50 chars
                # Only capture if it's NOT part of a traceback (no "Traceback", no "File")
                
                # Skip if this looks like a traceback fragment
                if ('File "' in line[:100] or 
                    'Traceback' in line[:100] or
                    re.match(r'^\s+(File|return|raise|def|class)', line.strip())):
                    i += 1
                    continue
                
                # This is a standalone error (not a traceback)
                timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})', line)
                timestamp = timestamp_match.group(1) if timestamp_match else None
                
                # Determine severity from keywords in line
                line_upper = line.upper()
                if 'CRITICAL' in line_upper:
                    severity = 'CRITICAL'
                elif 'FAILED' in line_upper or 'EXCEPTION' in line_upper:
                    severity = 'ERROR'  # Treat FAILED/EXCEPTION as ERROR
                else:
                    severity = 'ERROR'
                
                # Start with the error line
                error_block = [line]
                
                # Look for continuation lines (same timestamp, no ERROR prefix)
                j = i + 1
                while j < len(lines) and j < i + 50:
                    next_line = lines[j]
                    
                    # Stop at next log entry
                    if re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', next_line):
                        break
                    
                    # Stop at empty line
                    if not next_line.strip():
                        break
                    
                    error_block.append(next_line)
                    j += 1
                
                error_text = '\n'.join(error_block)
                
                if len(error_block) > 0 and len(error_text) > 20:
                    errors.append({
                        'pod_name': pod_name,
                        'service': service,
                        'pod_type': pod_type,
                        'timestamp': timestamp,
                        'severity': severity,
                        'error_text': error_text,
                        'normalized_text': self._normalize_error_text(error_text),
                        'has_traceback': False
                    })
                    
                    context_before_count = len(context_lines_before)
                    context_after_count = len(context_lines_after)
                    if context_before_count > 0 or context_after_count > 0:
                        logger.debug(f"Extracted standalone error ({context_before_count} before, {context_after_count} after) from {pod_name}")
                    else:
                        logger.debug(f"Extracted standalone error from {pod_name}")
                
                i = j
            else:
                i += 1
        
        return errors
    
    def parse_pod_logs(self, pod_name: str, service: str, since_time: datetime, pod_type: str = 'openstack') -> List[Dict]:
        """
        Parse logs from a specific pod and extract error blocks.
        
        Args:
            pod_name: Name of the pod
            service: Service name (e.g., 'octavia', 'designate')
            since_time: Only get logs from this time onwards
            pod_type: Type of pod ('openstack' or 'test')
        
        Returns:
            List of error dictionaries
        """
        try:
            # Format timestamp for oc logs --since-time
            since_str = since_time.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
            
            cmd = [
                'oc', 'logs',
                pod_name,
                '-n', self.namespace,
                '--since-time', since_str,
                '--tail', '-1'  # Get all logs since time
            ]
            
            logger.debug(f"Getting logs for {pod_name} since {since_str}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                logger.warning(f"Failed to get logs for {pod_name}: {result.stderr}")
                return []
            
            log_text = result.stdout
            if not log_text.strip():
                logger.debug(f"No logs found for {pod_name}")
                return []
            
            errors = self._extract_error_blocks(log_text, pod_name, service, pod_type)
            
            if errors:
                with_traceback = sum(1 for e in errors if e.get('has_traceback'))
                pod_type_label = "test" if pod_type == "test" else "service"
                logger.info(f"Found {len(errors)} error(s) in {pod_name} ({pod_type_label} pod, {with_traceback} with full tracebacks)")
            
            return errors
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout getting logs for {pod_name}")
            return []
        except Exception as e:
            logger.error(f"Error parsing logs for {pod_name}: {e}")
            return []
    
    def _deduplicate_errors(self, all_errors: List[Dict]) -> List[Dict]:
        """
        Deduplicate errors using fuzzy matching.
        
        Groups similar errors together and returns unique error groups with occurrence count.
        
        Args:
            all_errors: List of all error dictionaries
        
        Returns:
            List of unique error dictionaries with 'count' and 'occurrences' fields
        """
        if not all_errors:
            return []
        
        logger.info(f"Deduplicating {len(all_errors)} errors using fuzzy matching (threshold: {self.similarity_threshold}%)...")
        start_time = datetime.now()
        
        unique_errors = []
        total = len(all_errors)
        
        for idx, error in enumerate(all_errors, 1):
            # Log progress every 100 errors
            if idx % 100 == 0 or idx == total:
                logger.info(f"  Progress: {idx}/{total} errors processed ({len(unique_errors)} unique so far)...")
            # Check if this error is similar to any existing unique error
            found_match = False
            
            for unique_error in unique_errors:
                similarity = self._calculate_similarity(
                    error['normalized_text'],
                    unique_error['normalized_text']
                )
                
                if similarity >= self.similarity_threshold:
                    # This is a duplicate - increment count and track occurrences
                    unique_error['count'] += 1
                    unique_error['occurrences'].append({
                        'pod_name': error['pod_name'],
                        'timestamp': error['timestamp']
                    })
                    
                    # Update last_seen
                    if error['timestamp']:
                        if not unique_error['last_seen'] or error['timestamp'] > unique_error['last_seen']:
                            unique_error['last_seen'] = error['timestamp']
                    
                    found_match = True
                    break
            
            if not found_match:
                # This is a new unique error
                unique_errors.append({
                    'pod_name': error['pod_name'],
                    'service': error['service'],
                    'pod_type': error.get('pod_type', 'openstack'),
                    'severity': error['severity'],
                    'error_text': error['error_text'],
                    'normalized_text': error['normalized_text'],
                    'first_seen': error['timestamp'],
                    'last_seen': error['timestamp'],
                    'count': 1,
                    'occurrences': [{
                        'pod_name': error['pod_name'],
                        'timestamp': error['timestamp']
                    }]
                })
        
        # Sort by severity (CRITICAL first) then by count (most frequent first)
        unique_errors.sort(key=lambda x: (
            0 if x['severity'] == 'CRITICAL' else 1,
            -x['count']
        ))
        
        # Log completion time
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Deduplication complete: {len(all_errors)} errors → {len(unique_errors)} unique (took {duration:.1f}s)")
        
        return unique_errors
    
    def collect_all_errors(self, since_time: datetime, service_filter: Optional[str] = None) -> Dict:
        """
        Collect and deduplicate errors from all OpenStack pods.
        
        Args:
            since_time: Only collect errors from this time onwards
            service_filter: Only collect from this specific service (e.g., 'octavia', 'designate')
                           If None, collects from all OpenStack pods
        
        Returns:
            Dictionary with error analysis results
        """
        pods = self.detect_openstack_pods()
        
        if not pods:
            logger.warning("No OpenStack pods to analyze for errors")
            return {
                'total_errors': 0,
                'unique_errors': [],
                'pods_analyzed': []
            }
        
        # Filter pods by service if specified
        if service_filter:
            filtered_pods = [p for p in pods if p['service'] == service_filter]
            if filtered_pods:
                logger.info(f"Filtering error collection to service: {service_filter}")
                pods = filtered_pods
            else:
                logger.warning(f"No pods found for service '{service_filter}', analyzing all pods")
        
        all_errors = []
        pods_analyzed = []
        
        for pod_info in pods:
            pod_name = pod_info['name']
            service = pod_info['service']
            pod_type = pod_info.get('type', 'openstack')
            
            logger.info(f"Collecting errors from {pod_name}...")
            errors = self.parse_pod_logs(pod_name, service, since_time=since_time, pod_type=pod_type)
            
            if errors:
                all_errors.extend(errors)
                pods_analyzed.append(pod_name)
        
        # Deduplicate errors
        unique_errors = self._deduplicate_errors(all_errors)
        
        # Calculate statistics
        total_errors = len(all_errors)
        unique_count = len(unique_errors)
        critical_count = sum(1 for e in unique_errors if e['severity'] == 'CRITICAL')
        
        # Group by service
        by_service = defaultdict(int)
        for error in all_errors:
            by_service[error['service']] += 1
        
        return {
            'total_errors': total_errors,
            'unique_errors': unique_errors,
            'unique_count': unique_count,
            'critical_count': critical_count,
            'pods_analyzed': pods_analyzed,
            'by_service': dict(by_service),
            'since_time': since_time.isoformat()
        }

