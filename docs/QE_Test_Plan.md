# QE Test Plan: OpenStack Tempest Monitoring Tool

## Test Coverage

This automated testing tool provides comprehensive monitoring and analysis for OpenStack Tempest test execution with the following coverage:

### 1. **Functional Testing Coverage**
- **OpenStack API Integration Tests**: Executes Tempest test suites targeting specific OpenStack services (Designate, Octavia, Neutron, Nova, etc.)
- **RBAC (Role-Based Access Control) Tests**: Validates permission models and security policies
- **Scenario Tests**: Multi-component integration scenarios
- **API Validation Tests**: REST API endpoint validation and response verification

### 2. **Performance & Stability Monitoring**
- **Pod Resource Monitoring**: CPU, memory usage, and restart detection across all OpenStack pods
- **API Performance Analysis**: Response times, error rates, and throughput for API endpoints
- **Test Execution Timing**: Individual test duration tracking and performance regression detection
- **System Stability**: Continuous monitoring for service crashes, OOM events, and pod restarts

### 3. **Error & Log Analysis**
- **Error Log Collection**: Automated extraction of ERROR/CRITICAL logs from OpenStack services
- **Error Deduplication**: Fuzzy matching to group similar errors and identify unique issues
- **Traceback Analysis**: Full Python traceback extraction for debugging
- **Service Health**: Cross-service error correlation and impact analysis

### 4. **Long-Running Stability Tests**
- **Soak Testing**: Continuous test execution for extended periods (hours to days)
- **Iteration-Based Testing**: Multiple test loops to detect intermittent failures
- **Regression Detection**: Track failure patterns across iterations

---

## Test Execution Steps

### Prerequisites
| Item | Requirement | Verification Command |
|------|------------|---------------------|
| OpenShift Cluster | Running cluster with OpenStack deployed | `oc cluster-info` |
| OpenStack Namespace | Pods in 'openstack' namespace | `oc get pods -n openstack` |
| Python Environment | Python 3.6+ with required packages | `python --version && pip list` |
| Cluster Access | Admin/cluster-admin role | `oc whoami && oc auth can-i get pods -n openstack` |
| CR Files | Valid Tempest Custom Resource YAML files | `ls CR_files/*.yaml` |

---

## Test Execution Table

| Step # | Test Action | Command / Procedure | Expected Result | Pass/Fail Criteria |
|--------|------------|---------------------|-----------------|-------------------|
| **1** | **Initial Setup** | | | |
| 1.1 | Clone repository | `git clone https://github.com/zahlabut/RunTempestMonitorPods.git && cd RunTempestMonitorPods` | Repository cloned successfully | Directory contains `main.py`, `config.yaml` |
| 1.2 | Install dependencies | `pip install -r requirements.txt` | All packages installed without errors | Exit code 0, no error messages |
| 1.3 | Verify OpenShift access | `oc get pods -n openstack` | List of OpenStack pods displayed | At least 10+ pods in Running state |
| 1.4 | Prepare CR files | Copy Tempest CR YAML files to `CR_files/` directory | Files copied successfully | `ls CR_files/*.yaml` shows at least 1 file |
| 1.5 | Configure test parameters | Edit `config.yaml`: set `time_to_run_hours`, `cr_files`, `namespace` | Config file updated | Valid YAML syntax, paths exist |
| **2** | **Execute Short Test Run (Validation)** | | | |
| 2.1 | Start test execution | `python main.py --config config.yaml` | Test execution begins, logs displayed | <ul><li>Timestamp logged</li><li>Pod monitoring started</li><li>CRs applied successfully</li></ul> |
| 2.2 | Monitor real-time logs | Observe console output during execution | <ul><li>Pod metrics logged every 30s</li><li>Test progress displayed</li><li>CR status updates shown</li></ul> | <ul><li>No Python exceptions</li><li>Metrics show CPU/memory values</li><li>CRs reach "Ready" state</li></ul> |
| 2.3 | Wait for test completion | Let tests run for configured duration | Tests complete naturally or reach time limit | <ul><li>"Test execution completed" message</li><li>No hanging processes</li></ul> |
| 2.4 | Verify results directory | `ls -lh results/` | Results directory populated with files | <ul><li>CSV files: metrics, results, failed_tests, test_execution_times</li><li>HTML files: graphs</li><li>ZIP archive: results_archive_*.zip</li><li>web_report/ directory</li></ul> |
| **3** | **Validate Generated Reports** | | | |
| 3.1 | Check CSV data integrity | `head -20 results/*.csv` | CSV files contain headers and data rows | <ul><li>Valid CSV format</li><li>Timestamps present</li><li>No empty files</li></ul> |
| 3.2 | Verify test results | `grep -i "failed\|passed" results/tempest_monitoring_results_*.csv` | Test outcomes recorded | Each CR has: testsPassed, testsFailed, testsSkipped counts |
| 3.3 | Review failed tests | `cat results/tempest_monitoring_failed_tests_*.csv` | Failed tests listed with details | Columns: timestamp, cr_name, test_name, duration, iteration, logged_line |
| 3.4 | Check pod metrics | `cat results/tempest_monitoring_metrics_*.csv \| head -50` | Resource metrics collected | Columns: timestamp, pod_name, namespace, cpu_usage, memory_usage, restarts, status |
| 3.5 | Verify test execution times | `cat results/tempest_monitoring_test_execution_times_*.csv \| head -20` | Individual test timings captured | Columns: timestamp, test_name, duration_seconds, status, cr_name |
| 3.6 | Review API performance data | `cat results/api_requests_*.csv \| head -20` | API requests logged (if available) | Columns: timestamp, service, pod, method, endpoint, status_code, response_time, is_error |
| 3.7 | Check error logs | `cat results/error_log_*.csv` (if exists) | Unique errors extracted and deduplicated | Columns: severity, service, pod_type, pod_name, first_seen, last_seen, count, error_text |
| **4** | **Validate Interactive Web Report** | | | |
| 4.1 | Extract results archive | `cd results && unzip results_archive_*.zip -d extracted && cd extracted` | Archive extracted successfully | <ul><li>index.html at root</li><li>src/ directory with graphs and CSVs</li></ul> |
| 4.2 | Open web report | `python -m http.server 8080` then open `http://localhost:8080/index.html` | Web report displays in browser | <ul><li>Summary statistics visible</li><li>4 stat cards: Total Tests, Passed, Failed, Skipped</li><li>Success rate calculated</li></ul> |
| 4.3 | Verify summary statistics | Check top stat cards | Numbers match CSV data | <ul><li>Total Tests = sum of all tests</li><li>Success Rate = Passed/(Passed+Failed)%</li><li>Skipped tests excluded from rate</li></ul> |
| 4.4 | Test graph navigation | Click "Open Graph →" for each graph | Each graph opens in new tab | <ul><li>Pod Metrics graph</li><li>Test Results graph</li><li>Test Execution Times graph</li><li>API Performance graph (if API data exists)</li><li>Error Report (if errors exist)</li></ul> |
| 4.5 | Verify "Back to Summary" button | Click "← Back to Summary" on any graph | Returns to index.html | Button visible at TOP of page, navigation works |
| 4.6 | Test CSV downloads | Click CSV file links in web report | CSVs download successfully | Files open in Excel/LibreOffice without errors |
| **5** | **Validate Interactive Graphs** | | | |
| 5.1 | Pod Metrics graph | Open pod_metrics_*.html | 3-subplot graph displays | <ul><li>CPU Usage over Time (line chart)</li><li>Memory Usage over Time (line chart)</li><li>Pod Restarts (bar chart)</li><li>Interactive zoom/pan works</li></ul> |
| 5.2 | Test Results graph | Open test_results_*.html | Stacked bar chart displays | <ul><li>Bars show Passed (green), Failed (red), Skipped (orange)</li><li>X-axis: Run #N with timestamps</li><li>Hover shows exact counts</li></ul> |
| 5.3 | Test Execution Times graph | Open test_execution_times_*.html | Scatter plot displays | <ul><li>Points color-coded by status</li><li>Hover shows test name, duration, status</li><li>Tests sorted by duration</li></ul> |
| 5.4 | API Performance graph | Open api_performance_*.html (if exists) | Multi-subplot graph displays | <ul><li>Response Times timeline (if timing data available)</li><li>Response Code Distribution (bar chart)</li><li>Error Rate Timeline (line + markers)</li><li>Error Requests Table (sortable)</li><li>Hover on error markers shows URL</li></ul> |
| 5.5 | Error Report | Open error_report_*.html (if exists) | Error report displays | <ul><li>Statistics cards (Total, Unique, Critical, Pods Analyzed)</li><li>Errors grouped by pod name</li><li>Each error shows: severity, occurrences, timestamps, full text</li><li>Keywords highlighted in RED</li><li>Banner: "Analyzing LAST ITERATION ONLY"</li></ul> |
| **6** | **Test Interruption & Recovery** | | | |
| 6.1 | Interrupt running test | Start `python main.py`, wait 5 minutes, press `Ctrl+C` | Graceful shutdown initiated | <ul><li>"Shutdown signal received" message</li><li>Pod monitoring stops</li><li>Partial results saved to CSV</li></ul> |
| 6.2 | Verify partial results | `ls -lh results/` | CSV files exist with partial data | <ul><li>Metrics CSV has data up to interruption point</li><li>Results CSV has completed CRs only</li><li>No corrupted files</li></ul> |
| 6.3 | Run recovery script | `python generate_reports.py --results-dir results` | Reports regenerated from existing CSVs | <ul><li>"Found X CSV files" message</li><li>Graphs regenerated</li><li>Web report created</li><li>New ZIP archive created</li></ul> |
| 6.4 | Verify recovered report | Open regenerated `results/web_report/index.html` | Report displays correctly | <ul><li>Statistics match CSV data</li><li>All graphs regenerated</li><li>No duplicate graph links</li></ul> |
| **7** | **Long-Running Stability Test** | | | |
| 7.1 | Configure long run | Set `time_to_run_hours: 12` in config.yaml | Config updated | File saved, valid YAML |
| 7.2 | Start background execution | `nohup python main.py --config config.yaml > output.log 2>&1 &` | Test runs in background | <ul><li>Process ID returned</li><li>output.log created</li><li>`ps aux \| grep main.py` shows process</li></ul> |
| 7.3 | Monitor progress remotely | `tail -f output.log` | Real-time log output displayed | <ul><li>Pod metrics logged periodically</li><li>CR iterations increment</li><li>No error messages</li></ul> |
| 7.4 | Check for pod restarts | Review pod_metrics_*.html after completion | Restart events captured | <ul><li>Restart count increases if pods crash</li><li>Timestamp of restart visible</li></ul> |
| 7.5 | Analyze failure trends | Review failed_tests_*.csv for patterns | Intermittent failures detected | <ul><li>Same test failing across iterations = regression</li><li>Different tests failing = flaky environment</li></ul> |
| 7.6 | Review error correlation | Open error_report_*.html | Unique errors identified | <ul><li>Repeated errors across iterations grouped together</li><li>Error count shows frequency</li><li>Service-level error breakdown displayed</li></ul> |
| **8** | **Remote File Download (from Controller)** | | | |
| 8.1 | Download results from controller | `ssh bastion "ssh controller-0 'cd /path/to/RunTempestMonitorPods/results && base64 results_archive_*.zip'" \| base64 -d > results.zip` | ZIP file downloaded to local machine | File size > 0, no corruption |
| 8.2 | Verify ZIP integrity | `unzip -t results.zip` | ZIP file is valid | "No errors detected in compressed data" |
| 8.3 | Extract and view locally | `unzip results.zip && python -m http.server 8080` | Reports viewable on local machine | Web report opens in browser, all graphs functional |
| **9** | **Negative Test Cases** | | | |
| 9.1 | Invalid CR file | Run with non-existent CR file path in config | Error handled gracefully | <ul><li>Clear error message</li><li>Script exits with non-zero code</li><li>No Python traceback</li></ul> |
| 9.2 | Missing namespace | Run with invalid/missing namespace | Error handled gracefully | <ul><li>"No pods found" or similar message</li><li>Script continues or exits cleanly</li></ul> |
| 9.3 | Network interruption | Simulate network loss during execution | Reconnection or graceful failure | <ul><li>`oc` commands fail with clear errors</li><li>Script doesn't hang indefinitely</li></ul> |
| 9.4 | Disk space full | Run with full results directory | Error reported | <ul><li>"No space left on device" error</li><li>Script exits gracefully</li></ul> |
| 9.5 | Invalid config YAML | Edit config.yaml with syntax errors | YAML parsing error reported | <ul><li>Clear error message identifying syntax issue</li><li>Line number of error (if possible)</li></ul> |

---

## Expected Deliverables

| Deliverable | Description | Location | Format |
|------------|-------------|----------|--------|
| **CSV Files** | Raw data exports | `results/*.csv` | CSV (comma-delimited) |
| - Pod Metrics | CPU, memory, restarts for all pods | `tempest_monitoring_metrics_*.csv` | Time-series data |
| - Test Results | CR-level test outcomes | `tempest_monitoring_results_*.csv` | Per-CR summary |
| - Failed Tests | Individual failed test details | `tempest_monitoring_failed_tests_*.csv` | Test-level data |
| - Test Execution Times | Performance timing for each test | `tempest_monitoring_test_execution_times_*.csv` | Test-level data |
| - API Requests | API-level performance data | `api_requests_*.csv` | Request-level data |
| - Error Logs | Deduplicated error blocks | `error_log_*.csv` | Error-level data |
| **HTML Graphs** | Interactive visualizations | `results/*.html` | Plotly HTML |
| - Pod Metrics | 3-subplot resource monitoring | `pod_metrics_*.html` | Interactive graph |
| - Test Results | Pass/Fail/Skip trends | `test_results_*.html` | Interactive graph |
| - Test Execution | Individual test timings | `test_execution_times_*.html` | Interactive graph |
| - API Performance | API monitoring (3-4 subplots) | `api_performance_*.html` | Interactive graph |
| - Error Report | Grouped error analysis | `error_report_*.html` | Interactive report |
| **Web Report** | Unified dashboard | `results/web_report/` | HTML + assets |
| - Summary Page | Main dashboard with statistics | `web_report/index.html` | HTML page |
| - Assets | All graphs, CSVs, images | `web_report/src/` | Mixed formats |
| **Archive** | Portable results package | `results/results_archive_*.zip` | ZIP archive |
| - Complete Package | All reports + data in single file | Ready for download/sharing | Self-contained |

---

## Success Criteria

### Functional Success
- ✅ All CRs execute successfully (or with expected failures)
- ✅ Test results accurately captured in CSV files
- ✅ Failed tests logged with full details
- ✅ No script crashes or unhandled exceptions

### Performance Success
- ✅ Pod metrics collected without gaps (30s sampling)
- ✅ API response times captured (if available in logs)
- ✅ Test execution times match Tempest log data
- ✅ Monitoring overhead < 5% CPU/memory

### Data Integrity Success
- ✅ All CSV files contain valid, parseable data
- ✅ Timestamps are consistent and chronological
- ✅ No duplicate or missing data points
- ✅ ZIP archive extracts without errors

### Reporting Success
- ✅ Web report displays correctly in major browsers
- ✅ All graphs render and are interactive
- ✅ Navigation links work correctly
- ✅ Summary statistics match raw CSV data
- ✅ Error report shows unique errors only (deduplicated)

### Stability Success
- ✅ Tool runs for configured duration without crashes
- ✅ Graceful shutdown on interruption (Ctrl+C)
- ✅ Recovery script successfully regenerates reports
- ✅ Long-running tests (12+ hours) complete successfully

---

## Known Limitations

| Limitation | Description | Workaround |
|-----------|-------------|------------|
| **API Timing Data** | Some OpenStack services use Apache/WSGI logs without response time | Accept 0.0 response times, focus on error rates and status codes |
| **Restart Detection** | Deployment-based pods with changing names may not track restarts accurately | Use StatefulSet pods for critical services, or monitor by label selector |
| **Log Parsing** | Non-standard log formats may not be captured by error collector | Manually review logs for unstructured errors |
| **Time-based Filtering** | `oc logs --since-time` requires server-side support | Falls back to tail if unavailable (less accurate) |
| **Resource Overhead** | Error collection can take 5-10 minutes for large deployments | Only analyzes last iteration, not entire run |

---

## Troubleshooting Guide

| Issue | Possible Cause | Resolution |
|-------|----------------|------------|
| No graphs generated | Kaleido/Chrome not installed | Run `pip install kaleido` or `plotly_get_chrome` |
| Empty CSV files | No test execution or monitoring | Check CR files are valid, verify namespace |
| Duplicate graphs in index.html | Old HTML files not cleaned up | Delete old `*.html` files from results/ directory |
| Missing error report | No ERROR/CRITICAL logs found | This is expected if services are healthy |
| ZIP download corrupted | Binary transfer over SSH | Use base64 encoding: `base64 file.zip \| base64 -d` |
| Tests not starting | CR already exists in cluster | Delete old CRs: `oc delete -f CR_files/*.yaml` |

---

## Integration with CI/CD

This tool can be integrated into automated pipelines:

```yaml
# Example Jenkins/GitLab CI snippet
test-openstack-stability:
  stage: test
  script:
    - oc login --token=$OPENSHIFT_TOKEN
    - git clone https://github.com/zahlabut/RunTempestMonitorPods.git
    - cd RunTempestMonitorPods
    - pip install -r requirements.txt
    - cp /ci/cr_files/*.yaml CR_files/
    - python main.py --config ci_config.yaml
  artifacts:
    paths:
      - RunTempestMonitorPods/results/results_archive_*.zip
    expire_in: 30 days
  timeout: 24h
```

---

## References

- **GitHub Repository**: https://github.com/zahlabut/RunTempestMonitorPods
- **Tempest Documentation**: https://docs.openstack.org/tempest/latest/
- **OpenShift CLI Reference**: https://docs.openshift.com/container-platform/latest/cli_reference/
- **README**: See `README.md` in repository for detailed setup instructions

---

## Document Version

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-18 | QE Team | Initial test plan created |


