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
    
    def parse_api_logs(self, pod_name: str, service: str) -> List[Dict]:
        """
        Parse API logs from a pod to extract request information.
        
        Args:
            pod_name: Name of the API pod
            service: Service name (e.g., 'octavia', 'designate')
            
        Returns:
            List of request dictionaries
        """
        requests = []
        
        try:
            # Get pod logs
            cmd = ["oc", "logs", pod_name, "-n", self.namespace, "--tail=10000"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                logger.warning(f"Could not get logs for {pod_name}")
                return []
            
            logs = result.stdout
            
            # Common OpenStack API log patterns
            # Format: 2024-11-12 20:30:45.123 INFO [req-id] METHOD /path STATUS TIME
            patterns = [
                # Pattern 1: Standard OpenStack format
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+).*?"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+([^"]+)"\s+status:\s+(\d+)\s+len:\s+\d+\s+time:\s+([\d.]+)',
                # Pattern 2: Apache/WSGI format
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+).*?(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(\S+)\s+.*?\s+(\d{3})\s+([\d.]+)',
                # Pattern 3: Simpler format
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}).*?(GET|POST|PUT|DELETE|PATCH)\s+([^\s]+).*?(\d{3}).*?([\d.]+)s',
            ]
            
            for line in logs.split('\n'):
                for pattern in patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        try:
                            timestamp_str = match.group(1)
                            method = match.group(2).upper()
                            endpoint = match.group(3)
                            status_code = int(match.group(4))
                            response_time = float(match.group(5))
                            
                            # Parse timestamp
                            try:
                                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                            except ValueError:
                                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                            
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
            
            logger.info(f"Parsed {len(requests)} API requests from {pod_name}")
            return requests
            
        except Exception as e:
            logger.error(f"Error parsing logs for {pod_name}: {e}")
            return []
    
    def analyze_all_api_pods(self) -> Dict:
        """
        Analyze logs from all detected API pods.
        
        Returns:
            Dictionary with analysis results
        """
        api_pods = self.detect_api_pods()
        
        if not api_pods:
            logger.warning("No API pods to analyze")
            return {
                'total_requests': 0,
                'requests': [],
                'pods_analyzed': []
            }
        
        all_requests = []
        pods_analyzed = []
        
        for pod_info in api_pods:
            pod_name = pod_info['name']
            service = pod_info['service']
            
            logger.info(f"Analyzing API logs for {pod_name}...")
            requests = self.parse_api_logs(pod_name, service)
            
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

