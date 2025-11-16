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
        # These are the main OpenStack service pods
        self.pod_patterns = [
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
        
        # Similarity threshold for fuzzy matching (0-100)
        self.similarity_threshold = 85
    
    def detect_openstack_pods(self) -> List[Dict]:
        """
        Detect all running OpenStack service pods.
        
        Returns:
            List of dictionaries with pod info: {'name': str, 'service': str}
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
                
                # Check if pod matches any of our patterns and is running
                if phase == 'Running':
                    for pattern in self.pod_patterns:
                        if pattern in pod_name:
                            # Extract service name (e.g., 'octavia' from 'octavia-api-xyz')
                            service = pattern.split('-')[0]
                            detected_pods.append({
                                'name': pod_name,
                                'service': service
                            })
                            break
            
            if detected_pods:
                logger.info(f"Detected {len(detected_pods)} OpenStack pods for error collection")
                # Log unique services
                services = sorted(set(p['service'] for p in detected_pods))
                logger.info(f"Services: {', '.join(services)}")
            
            return detected_pods
            
        except Exception as e:
            logger.error(f"Error detecting OpenStack pods: {e}")
            return []
    
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
    
    def _extract_error_blocks(self, log_text: str, pod_name: str, service: str) -> List[Dict]:
        """
        Extract error blocks from log text.
        
        Args:
            log_text: Raw log text
            pod_name: Name of the pod
            service: Service name
        
        Returns:
            List of error dictionaries
        """
        errors = []
        lines = log_text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Check if line contains ERROR or CRITICAL
            if re.search(r'\b(ERROR|CRITICAL)\b', line, re.IGNORECASE):
                # Extract error block (current line + context)
                error_block = [line]
                
                # Look ahead for traceback/continuation lines (indented or starting with spaces)
                j = i + 1
                while j < len(lines) and j < i + 50:  # Limit to 50 lines per block
                    next_line = lines[j]
                    # Check if it's a continuation (traceback, indented, or part of multi-line error)
                    if (next_line.startswith('    ') or 
                        next_line.startswith('\t') or 
                        'Traceback' in next_line or
                        'File "' in next_line or
                        re.match(r'^\s+', next_line) or
                        (next_line and not re.search(r'\d{4}-\d{2}-\d{2}', next_line[:30]))):  # No new timestamp
                        error_block.append(next_line)
                        j += 1
                    else:
                        break
                
                # Extract timestamp from the first line
                timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})', line)
                timestamp = timestamp_match.group(1) if timestamp_match else None
                
                # Determine severity
                severity = 'CRITICAL' if 'CRITICAL' in line.upper() else 'ERROR'
                
                error_text = '\n'.join(error_block)
                
                errors.append({
                    'pod_name': pod_name,
                    'service': service,
                    'timestamp': timestamp,
                    'severity': severity,
                    'error_text': error_text,
                    'normalized_text': self._normalize_error_text(error_text)
                })
                
                # Skip processed lines
                i = j
            else:
                i += 1
        
        return errors
    
    def parse_pod_logs(self, pod_name: str, service: str, since_time: datetime) -> List[Dict]:
        """
        Parse logs from a specific pod and extract error blocks.
        
        Args:
            pod_name: Name of the pod
            service: Service name (e.g., 'octavia', 'designate')
            since_time: Only get logs from this time onwards
        
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
            
            errors = self._extract_error_blocks(log_text, pod_name, service)
            
            if errors:
                logger.info(f"Found {len(errors)} error(s) in {pod_name}")
            
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
        
        unique_errors = []
        
        for error in all_errors:
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
            
            logger.info(f"Collecting errors from {pod_name}...")
            errors = self.parse_pod_logs(pod_name, service, since_time=since_time)
            
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

