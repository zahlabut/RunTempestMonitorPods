# QE Test Plan: OpenStack Service Stability Testing

**Purpose**: Validate OpenStack service stability, performance, and functionality under continuous load using automated Tempest testing with comprehensive monitoring.

**Scope**: This test plan focuses on using the monitoring tool to validate OpenStack components (e.g., Designate, Octavia, Neutron) for production readiness.

---

## Test Objectives

1. **Functional Stability**: Verify OpenStack service APIs remain functional under continuous test load
2. **Memory Leak Detection**: Identify memory growth patterns in service pods over extended runs
3. **Performance Degradation**: Detect API response time increases or throughput reduction over time
4. **Error Pattern Analysis**: Identify recurring errors or service failures
5. **Resource Stability**: Monitor for pod crashes, OOM kills, or restart loops

---

## Test Scenario Example: Designate DNS Service - 72-Hour Stability Test

### Test Configuration

| Parameter | Value | Purpose |
|-----------|-------|---------|
| **Service Under Test** | Designate (DNS-as-a-Service) | Validate DNS service stability |
| **Test Duration** | 72 hours (3 days) | Detect long-term memory leaks and degradation |
| **Test Type** | Tempest integration tests in continuous loop | Exercise all Designate API endpoints |
| **Monitoring Interval** | 30 seconds | Track resource usage trends |
| **Test CRs** | `designate_neutron_integration_cr.yaml` | Designate + Neutron integration scenarios |

---

## Test Execution Steps

| Step | Action | Command / Details | What to Validate |
|------|--------|-------------------|------------------|
| **1. Setup** | Configure test environment | | |
| 1.1 | Clone tool repository | `git clone <repo> && cd RunTempestMonitorPods` | Tool files present |
| 1.2 | Install dependencies | `pip install -r requirements.txt` | No errors |
| 1.3 | Prepare Designate test CRs | Copy CR files to `CR_files/designate_*.yaml` | CRs validated |
| 1.4 | Configure test duration | Edit `config.yaml`: `time_to_run_hours: 72` | Duration set correctly |
| 1.5 | Verify target environment | `oc get pods -n openstack \| grep designate` | All Designate pods Running |
| **2. Execute** | Start long-running test | | |
| 2.1 | Launch test in background | `nohup python main.py --config config.yaml > designate_test.log 2>&1 &` | Process started, PID captured |
| 2.2 | Monitor execution progress | `tail -f designate_test.log` | See real-time metrics, test iterations |
| 2.3 | Verify continuous operation | Check log every 8-12 hours | Tests looping, no stuck processes |
| 2.4 | Wait for completion | Let run for full 72 hours | Execution completes naturally |
| **3. Analyze Results** | Download and review reports | | |
| 3.1 | Download results archive | `scp controller:/path/results_archive_*.zip .` | ZIP file downloaded |
| 3.2 | Extract and open web report | `unzip results_archive_*.zip && python -m http.server 8080` | Open `http://localhost:8080` |
| 3.3 | Review summary dashboard | Check `index.html` statistics | Note total tests, pass rate, failures |

---

## Analysis Checklist: What to Look For

### ✅ **1. Memory Leak Detection**

**Report**: `Pod Metrics` graph → Memory Usage Over Time

| Check | How to Validate | Pass Criteria | Fail Indicators |
|-------|----------------|---------------|-----------------|
| **Steady State Memory** | Open `pod_metrics_*.html`, view Memory subplot | Memory usage relatively flat (±10%) | Continuous upward trend (>20% increase) |
| **Service Pod Growth** | Check designate-api, designate-central, designate-worker | All pods remain under resource limits | Any pod shows linear growth over 72h |
| **Memory Spike Recovery** | Look for spikes that return to baseline | Memory returns after test iterations | Memory increases after each iteration, never drops |

**Example Analysis**:
```
✅ PASS: designate-api memory: 2.1Gi → 2.3Gi → 2.2Gi (stable oscillation)
❌ FAIL: designate-worker memory: 1.5Gi → 2.8Gi → 4.1Gi (linear growth = leak)
```

---

### ✅ **2. Functional Stability**

**Report**: `Test Results` graph + `failed_tests_*.csv`

| Check | How to Validate | Pass Criteria | Fail Indicators |
|-------|----------------|---------------|-----------------|
| **Consistent Pass Rate** | Review stacked bar chart | Success rate ≥ 95% across all iterations | Pass rate drops over time (e.g., 98% → 85%) |
| **No New Failures** | Compare failed tests across iterations | Same tests fail (known issues) | New tests start failing after 24h+ |
| **Failure Pattern** | Check `failed_tests_*.csv` for test names | Random failures (flaky tests) | Same tests fail repeatedly (regression) |

**Example Analysis**:
```
✅ PASS: Success rate: Iteration 1-100 = 97.2% ± 1.5% (stable)
❌ FAIL: Success rate: Iteration 1=98%, 50=94%, 100=89% (degrading)
```

---

### ✅ **3. API Performance Degradation**

**Report**: `API Performance Analysis` graph → Response Times Over Time

| Check | How to Validate | Pass Criteria | Fail Indicators |
|-------|----------------|---------------|-----------------|
| **Response Time Stability** | Check API response time trend | Median response time ±20% | Response times increase >50% over 72h |
| **Error Rate** | Review Error Rate Timeline subplot | Error rate < 5% consistently | Error rate climbs (e.g., 2% → 15%) |
| **Endpoint Health** | Check status code distribution | HTTP 2xx > 95% | Increasing 4xx or 5xx errors |

**Example Analysis**:
```
✅ PASS: POST /v2/zones: 0.15s → 0.18s → 0.16s (stable)
❌ FAIL: GET /v2/zones: 0.10s → 0.25s → 0.45s (degrading)
```

---

### ✅ **4. Service Error Analysis**

**Report**: `Error Report` (if generated)

| Check | How to Validate | Pass Criteria | Fail Indicators |
|-------|----------------|---------------|-----------------|
| **Error Uniqueness** | Count unique errors vs total occurrences | Few unique errors (known issues) | Many unique errors (instability) |
| **Critical Errors** | Filter for CRITICAL severity | Zero CRITICAL errors | Any CRITICAL errors present |
| **Error Frequency** | Check error occurrence counts | Low occurrence (<10 per error) | High occurrence (>100 per error) |
| **Traceback Analysis** | Review full tracebacks | Expected errors (timeouts, network) | Unexpected errors (NullPointer, corruption) |

**Example Analysis**:
```
✅ PASS: 3 unique errors, 15 total occurrences (flaky network)
❌ FAIL: 1 unique error, 1,247 occurrences (repeated failure in designate-worker)
```

---

### ✅ **5. Pod Stability**

**Report**: `Pod Metrics` graph → Pod Restarts subplot

| Check | How to Validate | Pass Criteria | Fail Indicators |
|-------|----------------|---------------|-----------------|
| **Zero Restarts** | Check restart bar chart | All pods show 0 restarts | Any pod restarts during test |
| **OOM Events** | Cross-reference restarts with memory graph | No restarts correlated with memory spikes | Restart occurs when memory hits limit |
| **Crash Loops** | Check for multiple restarts on same pod | No repeated restarts | Pod restarting multiple times |

**Example Analysis**:
```
✅ PASS: All 8 designate pods: 0 restarts over 72h
❌ FAIL: designate-worker-2: 12 restarts (OOMKilled events in logs)
```

---

### ✅ **6. Test Execution Performance**

**Report**: `Test Execution Times` graph

| Check | How to Validate | Pass Criteria | Fail Indicators |
|-------|----------------|---------------|-----------------|
| **Execution Time Stability** | Check test duration scatter plot | Test times relatively consistent | Test durations increase over time |
| **Slow Tests** | Identify outliers (hover over points) | Known slow tests remain slow | Previously fast tests become slow |

**Example Analysis**:
```
✅ PASS: test_zone_create: 0.5s → 0.6s → 0.5s (stable)
❌ FAIL: test_zone_create: 0.5s → 2.1s → 4.5s (slowing down)
```

---

## Expected Test Outcomes

### ✅ **PASS Criteria** (Service is Production-Ready)

- ✅ **Memory**: No linear growth >20% over 72 hours
- ✅ **Functionality**: Success rate ≥ 95% across all iterations
- ✅ **Performance**: API response times remain within ±20% of baseline
- ✅ **Stability**: Zero pod restarts or OOM events
- ✅ **Errors**: No CRITICAL errors, minimal unique ERROR occurrences

### ❌ **FAIL Criteria** (Service Needs Investigation)

- ❌ **Memory Leak**: Any pod shows continuous memory growth (>30% increase)
- ❌ **Functional Regression**: Pass rate drops >5% over time
- ❌ **Performance Degradation**: API response times increase >50%
- ❌ **Service Crashes**: Any pod restarts during test execution
- ❌ **Critical Errors**: CRITICAL log entries found in error report

---

## Sample Test Report (Designate 72h Run)

### Test Summary
- **Duration**: 72 hours (completed)
- **Total Test Iterations**: 324 loops
- **Total Tests Executed**: 45,360 tests
- **Overall Success Rate**: 96.8%
- **Failed Tests**: 1,451 failures
- **Unique Failures**: 12 distinct test failures

### Key Findings

| Component | Status | Details | Action Required |
|-----------|--------|---------|-----------------|
| **Memory Stability** | ✅ PASS | All pods stable (±5% variation) | None |
| **Functional Stability** | ✅ PASS | 96.8% pass rate (consistent) | None |
| **API Performance** | ⚠️ WARNING | POST /v2/zones response time increased 35% | Investigate database query performance |
| **Pod Restarts** | ✅ PASS | Zero restarts | None |
| **Error Analysis** | ❌ FAIL | 847 occurrences of "Connection pool timeout" | Scale up database connections |

### Recommendation
**Result**: Designate service is **STABLE** for production, with **1 performance issue** requiring optimization before release.

**Follow-up Actions**:
1. Investigate POST /v2/zones response time increase → Database query optimization
2. Review "Connection pool timeout" errors → Adjust MySQL max_connections setting
3. Re-run 72h test after fixes to confirm resolution

---

## Additional Test Scenarios

You can apply this same test plan to other OpenStack services:

| Service | Test CR Files | Focus Area | Typical Duration |
|---------|--------------|------------|------------------|
| **Octavia** | `octavia_tempest_*.yaml` | Load balancer creation/deletion, memory in amphora pods | 48-72 hours |
| **Neutron** | `neutron_tempest_*.yaml` | Network/subnet/port operations, OVN performance | 24-48 hours |
| **Nova** | `nova_tempest_*.yaml` | VM lifecycle, compute node stability | 48-96 hours |
| **Cinder** | `cinder_tempest_*.yaml` | Volume operations, storage backend health | 24-48 hours |

---

## Quick Reference: Key Files & Reports

| File | What It Shows | Primary Use Case |
|------|---------------|------------------|
| `index.html` | Overall test summary dashboard | Executive summary, pass/fail overview |
| `pod_metrics_*.html` | CPU, memory, restarts over time | Memory leak detection, resource stability |
| `test_results_*.html` | Pass/fail trends across iterations | Functional regression detection |
| `api_performance_*.html` | API response times, error rates | Performance degradation analysis |
| `error_report_*.html` | Unique errors grouped by pod | Root cause analysis for failures |
| `failed_tests_*.csv` | Individual failed test details | Identify specific test failures |
| `tempest_monitoring_metrics_*.csv` | Raw resource metrics | Detailed analysis, custom graphing |

---

## Troubleshooting Common Issues

| Issue | Likely Cause | Resolution |
|-------|--------------|------------|
| **Test stopped after 30min** | Config `time_to_run_hours` not set | Edit `config.yaml`, set desired duration |
| **No memory data in graphs** | Metrics not collected | Check OpenShift metrics-server installed |
| **All tests failing** | Service unavailable or CR invalid | Verify service pods running, test CR manually |
| **No error report generated** | No ERROR/CRITICAL logs found | Good news! Service ran cleanly |
| **High skip count** | Test dependencies missing | Expected for partial deployments |

---

## Document Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-18 | Initial product-focused test plan |
