"""
API Log Monitoring and Analysis Module

Analyzes OpenStack API pod logs to track request performance and error rates.
"""

import logging
import re
import subprocess
import json
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class APIMonitor:
    """Monitor and analyze API pod logs for performance and errors."""
    
    def __init__(self, namespace: str = "openstack"):
        """
        Initialize API Monitor.
        
        Args:
            namespace: Kubernetes namespace where API pods are running
        """
        self.namespace = namespace
        self.api_pod_patterns = [
            'octavia-api',
            'designate-api',
            'neutron-api',
            'nova-api',
            'cinder-api',
            'glance-api',
            'keystone-api'
        ]
    
    def detect_api_pods(self) -> List[Dict]:
        """
        Detect all API pods in the namespace.
        
        Returns:
            List of dictionaries with pod info (name, service)
        """
        api_pods = []
        
        try:
            cmd = ["oc", "get", "pods", "-n", self.namespace, "-o", "json"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            pods_data = json.loads(result.stdout)
            
            for pod in pods_data.get("items", []):
                pod_name = pod["metadata"]["name"]
                
                # Check if pod matches any API pattern
                for pattern in self.api_pod_patterns:
                    if pattern in pod_name and pod.get("status", {}).get("phase") == "Running":
                        # Determine service name
                        service = pattern.replace('-api', '')
                        api_pods.append({
                            'name': pod_name,
                            'service': service,
                            'pattern': pattern
                        })
                        logger.info(f"Detected API pod: {pod_name} (service: {service})")
                        break
            
            if not api_pods:
                logger.warning("No API pods detected in namespace")
            else:
                logger.info(f"Total API pods detected: {len(api_pods)}")
            
            return api_pods
            
        except Exception as e:
            logger.error(f"Error detecting API pods: {e}")
            return []
    
    def parse_api_logs(self, pod_name: str, service: str, since_time: Optional[datetime] = None) -> List[Dict]:
        """
        Parse API logs from a pod to extract request information.
        
        Args:
            pod_name: Name of the API pod
            service: Service name (e.g., 'octavia', 'designate')
            since_time: Test start time - REQUIRED for accurate analysis.
                       Only parses logs from this time onwards to exclude unrelated traffic.
            
        Returns:
            List of request dictionaries (empty if since_time not provided)
        """
        requests = []
        
        try:
            # Require start time for accurate analysis
            if not since_time:
                logger.error(f"Cannot analyze {pod_name} without test start time - analysis would be inaccurate")
                return []
            
            # Get pod logs using time-based filtering
            since_str = since_time.strftime('%Y-%m-%dT%H:%M:%SZ')
            cmd = ["oc", "logs", pod_name, "-n", self.namespace, f"--since-time={since_str}"]
            logger.info(f"Getting logs for {pod_name} since {since_str}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                logger.warning(f"Could not get logs for {pod_name}")
                return []
            
            logs = result.stdout
            
            # Common OpenStack API log patterns
            patterns = [
                # Pattern 1: Standard OpenStack format with timing (handles optional microversion field)
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+).*?"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+([^"]+)"\s+status:\s+(\d+)\s+len:\s+\d+.*?time:\s+([\d.]+)',
                # Pattern 2: Apache access log with timing in seconds at end
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+).*?(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(\S+)\s+.*?\s+(\d{3})\s+([\d.]+)',
                # Pattern 3: Simpler format with timing
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}).*?(GET|POST|PUT|DELETE|PATCH)\s+([^\s]+).*?(\d{3}).*?([\d.]+)s',
                # Pattern 4: Apache/WSGI access log format WITHOUT timing (e.g., "IP - - [DD/Mon/YYYY:HH:MM:SS +0000] "METHOD /path HTTP/1.1" STATUS ...")
                r'\[(\d{2}/\w+/\d{4}:\d{2}:\d{2}:\d{2})\s+[+\-]\d{4}\]\s+"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(\S+)\s+HTTP/[\d.]+"\s+(\d{3})',
            ]
            
            line_count = 0
            matched_count = 0
            for line in logs.split('\n'):
                # Look for lines that might be API requests
                if any(method in line.upper() for method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']):
                    line_count += 1
                    
                for pattern_idx, pattern in enumerate(patterns):
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        matched_count += 1
                        try:
                            timestamp_str = match.group(1)
                            method = match.group(2).upper()
                            endpoint = match.group(3)
                            status_code = int(match.group(4))
                            
                            # Pattern 4 (Apache access log) doesn't have timing, set to 0
                            if pattern_idx == 3:  # Pattern 4
                                response_time = 0.0
                            else:
                                response_time = float(match.group(5))
                            
                            # Parse timestamp based on format
                            try:
                                if '/' in timestamp_str:
                                    # Apache format: "12/Nov/2025:21:14:49"
                                    timestamp = datetime.strptime(timestamp_str, '%d/%b/%Y:%H:%M:%S')
                                elif '.' in timestamp_str:
                                    # ISO format with microseconds
                                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                                else:
                                    # ISO format without microseconds
                                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                            except ValueError as e:
                                logger.debug(f"Could not parse timestamp '{timestamp_str}': {e}")
                                continue
                            
                            # Skip healthcheck endpoints (Kubernetes probes)
                            if '/healthcheck' in endpoint.lower():
                                continue
                            
                            request_info = {
                                'timestamp': timestamp,
                                'pod_name': pod_name,
                                'service': service,
                                'method': method,
                                'endpoint': endpoint,
                                'status_code': status_code,
                                'response_time': response_time,
                                'is_error': status_code >= 400,
                                'is_client_error': 400 <= status_code < 500,
                                'is_server_error': status_code >= 500
                            }
                            
                            requests.append(request_info)
                        except (ValueError, IndexError) as e:
                            logger.debug(f"Could not parse log line: {e}")
                            continue
                        break
            
            if requests:
                # Count requests with and without timing
                with_timing = sum(1 for r in requests if r['response_time'] > 0)
                logger.info(f"Parsed {len(requests)} API requests from {pod_name} ({with_timing} with timing data)")
            else:
                logger.warning(f"No API requests found in {pod_name} logs (checked {len(logs.split(chr(10)))} lines, {line_count} HTTP method lines, {matched_count} pattern matches)")
                # Log first few unmatched lines for debugging
                if line_count > 0:
                    sample_lines = [l for l in logs.split('\n') if any(m in l.upper() for m in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])][:3]
                    logger.debug(f"Sample unmatched lines from {pod_name}:")
                    for i, sample in enumerate(sample_lines, 1):
                        logger.debug(f"  {i}. {sample[:200]}")
            
            return requests
            
        except Exception as e:
            logger.error(f"Error parsing logs for {pod_name}: {e}")
            return []
    
    def analyze_all_api_pods(self, since_time: Optional[datetime] = None, service_filter: Optional[str] = None) -> Dict:
        """
        Analyze logs from all detected API pods.
        
        Args:
            since_time: Test start time - REQUIRED for accurate analysis.
                       Only analyzes logs from this time onwards to exclude unrelated traffic.
            service_filter: Only analyze this specific service (e.g., 'octavia', 'designate').
                           Should be specified to avoid mixing irrelevant API data.
                           If None, analyzes all API pods (not recommended).
        
        Returns:
            Dictionary with analysis results (may have 0 requests if since_time not provided)
        """
        api_pods = self.detect_api_pods()
        
        if not api_pods:
            logger.warning("No API pods to analyze")
            return {
                'total_requests': 0,
                'requests': [],
                'pods_analyzed': []
            }
        
        # Filter pods by service if specified
        if service_filter:
            filtered_pods = [p for p in api_pods if p['service'] == service_filter]
            if filtered_pods:
                logger.info(f"Filtering API analysis to service: {service_filter}")
                api_pods = filtered_pods
            else:
                logger.warning(f"No API pods found for service '{service_filter}', analyzing all pods")
        
        all_requests = []
        pods_analyzed = []
        
        for pod_info in api_pods:
            pod_name = pod_info['name']
            service = pod_info['service']
            
            logger.info(f"Analyzing API logs for {pod_name}...")
            requests = self.parse_api_logs(pod_name, service, since_time=since_time)
            
            if requests:
                all_requests.extend(requests)
                pods_analyzed.append(pod_name)
        
        # Calculate statistics
        total_requests = len(all_requests)
        error_requests = sum(1 for r in all_requests if r['is_error'])
        client_errors = sum(1 for r in all_requests if r['is_client_error'])
        server_errors = sum(1 for r in all_requests if r['is_server_error'])
        
        # Calculate average response times
        if all_requests:
            avg_response_time = sum(r['response_time'] for r in all_requests) / total_requests
            max_response_time = max(r['response_time'] for r in all_requests)
            min_response_time = min(r['response_time'] for r in all_requests)
        else:
            avg_response_time = 0
            max_response_time = 0
            min_response_time = 0
        
        # Group by service
        by_service = defaultdict(list)
        for req in all_requests:
            by_service[req['service']].append(req)
        
        analysis = {
            'total_requests': total_requests,
            'error_requests': error_requests,
            'client_errors': client_errors,
            'server_errors': server_errors,
            'success_rate': ((total_requests - error_requests) / total_requests * 100) if total_requests > 0 else 0,
            'avg_response_time': avg_response_time,
            'max_response_time': max_response_time,
            'min_response_time': min_response_time,
            'requests': all_requests,
            'by_service': dict(by_service),
            'pods_analyzed': pods_analyzed
        }
        
        logger.info(f"API Analysis Complete:")
        logger.info(f"  Total Requests: {total_requests}")
        logger.info(f"  Error Requests: {error_requests}")
        logger.info(f"  Success Rate: {analysis['success_rate']:.2f}%")
        logger.info(f"  Avg Response Time: {avg_response_time:.3f}s")
        
        return analysis

