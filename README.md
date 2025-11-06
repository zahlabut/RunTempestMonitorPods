# OpenStack Tempest Test Runner with Pod Monitoring V1 

A Python-based tool for running OpenStack Tempest tests via OpenShift Custom Resources (CRs) with comprehensive pod monitoring and metrics collection.

## Features

- 🚀 **Parallel Test Execution**: Run multiple Tempest test CRs in parallel
- 🔄 **Continuous Loop Testing**: Run tests continuously for a specified duration
- 📊 **Pod Monitoring**: Monitor pod status, CPU, and memory usage in real-time
- 📈 **Data Visualization**: Generate interactive graphs and static plots
- 💾 **CSV Export**: Export all metrics and results to CSV files
- ✅ **Test Verification**: Automatically verify test results (PASS/FAIL)
- 🛡️ **Failure Handling**: Log failures without interrupting the test process
- ⏰ **Configurable Duration**: Set test run duration in hours
- 🎯 **Pod Pattern Matching**: Monitor specific pods using wildcard patterns

## Requirements

- Python 3.8+
- OpenShift CLI (`oc`) installed and configured
- Access to OpenShift/Kubernetes cluster with proper permissions
- OpenStack Platform 18 (OSP18) setup

## Installation

1. Clone this repository:
```bash
git clone https://github.com/zahlabut/RunTempestMonitorPods.git
cd RunTempestMonitorPods
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your OpenShift CLI:
```bash
oc login -u system:admin
oc project openstack
```

## Configuration

Edit `config.yaml` to customize the test runner:

```yaml
# List of CR files to run
cr_files:
  - "designate_neutron_integration_cr.yaml"
  - "designate_tempest_plugin_cr.yaml"

# Duration to run tests (in hours)
time_to_run_hours: 2

# Pod monitoring configuration
monitoring:
  namespace: "openstack"
  pod_patterns:
    - "designate-*"
  interval_seconds: 30

# OpenShift configuration
openshift:
  cr_timeout: 3600
  cr_namespace: "openstack"

# Output configuration
output:
  results_dir: "results"
  csv_filename: "tempest_monitoring"
  enable_graphs: true
  graph_format: "png"

# Logging
logging:
  level: "INFO"
  log_file: "tempest_runner.log"
```

### Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `cr_files` | List of Custom Resource YAML files to apply | `[]` |
| `time_to_run_hours` | Duration to run tests in hours | `2` |
| `monitoring.namespace` | Namespace where pods are running | `openstack` |
| `monitoring.pod_patterns` | Pod name patterns to monitor (supports wildcards) | `["designate-*"]` |
| `monitoring.interval_seconds` | How often to collect metrics | `30` |
| `openshift.cr_timeout` | Timeout for CR completion in seconds | `3600` |
| `openshift.cr_namespace` | Namespace where CRs are created | `openstack` |
| `output.results_dir` | Directory for output files | `results` |
| `output.enable_graphs` | Enable graph generation | `true` |
| `output.graph_format` | Graph format (png, svg, pdf) | `png` |
| `logging.level` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` |

## Custom Resource Files

Create your CR files for the Tempest tests you want to run. Example CR files are provided:
- `designate_tempest_plugin_cr.yaml` - Designate zones and recordsets tests
- `designate_neutron_integration_cr.yaml` - Designate blacklists and pool tests

### Example CR Structure

```yaml
apiVersion: test.openstack.org/v1beta1
kind: Tempest
metadata:
  name: my-tempest-test
  namespace: openstack
spec:
  openStackConfigMap: openstack-config
  openStackConfigSecret: openstack-config-secret
  containerImage: quay.io/podified-antelope-centos9/openstack-tempest:current-podified
  includeList: |
    tempest.api.compute.test_servers
  parallel: true
  resources:
    requests:
      memory: "2Gi"
      cpu: "1000m"
    limits:
      memory: "4Gi"
      cpu: "2000m"
```

## Usage

### Basic Usage

Run with default configuration:

```bash
python main.py
```

### Custom Configuration

Run with a custom configuration file:

```bash
python main.py --config my_config.yaml
```

### Running in Background

Run the test runner in the background:

```bash
nohup python main.py > output.log 2>&1 &
```

### Graceful Shutdown

The tool supports graceful shutdown. Press `Ctrl+C` to stop:
- Current test runs will complete
- Final metrics will be collected
- Graphs will be generated
- Summary will be displayed

## Output

### Directory Structure

After running, the `results/` directory will contain:

```
results/
├── tempest_monitoring_metrics_20250105_143022.csv
├── tempest_monitoring_results_20250105_143022.csv
├── pod_metrics_20250105_153045.html
├── pod_metrics_20250105_153045.png
├── test_results_20250105_153045.html
└── test_results_20250105_153045.png
```

### CSV Files

#### Metrics CSV (`*_metrics_*.csv`)

Contains pod monitoring data:

| Column | Description |
|--------|-------------|
| `timestamp` | When the metric was collected |
| `pod_name` | Name of the pod |
| `phase` | Pod phase (Running, Pending, etc.) |
| `ready` | Ready containers (e.g., "1/1") |
| `restarts` | Number of container restarts |
| `cpu` | CPU usage (e.g., "100m") |
| `memory` | Memory usage (e.g., "256Mi") |

#### Results CSV (`*_results_*.csv`)

Contains test results:

| Column | Description |
|--------|-------------|
| `timestamp` | When the test completed |
| `cr_name` | Name of the Custom Resource |
| `passed` | Whether the test passed (True/False) |
| `phase` | Test phase/status |
| `tests_passed` | Number of tests passed |
| `tests_failed` | Number of tests failed |
| `tests_skipped` | Number of tests skipped |
| `message` | Status message or error |

### Graphs

The tool generates interactive HTML graphs and static images for visualization.

#### Pod Metrics Graph

Interactive HTML graph showing:
- **CPU usage over time** (per pod) - Track resource consumption
- **Memory usage over time** (per pod) - Monitor memory footprint
- **Container restarts over time** (per pod) - Detect stability issues

The graph displays multiple pods on a single interactive chart with:
- Individual lines for each pod being monitored
- Hover tooltips showing exact values at any point in time
- Zoom and pan capabilities for detailed analysis
- Legend to show/hide specific pods
- Time-series data captured at configured intervals

**Example Graph:**

![Pod Metrics Example](docs/pod_metrics_example.png)

**What to look for in the graph:**
- 📈 **Steady CPU/Memory**: Normal test execution
- 🔴 **Spikes in CPU/Memory**: Heavy operations or potential issues
- ⚠️ **Increasing restarts**: Pod stability problems
- 📊 **Patterns over iterations**: Performance consistency

#### Test Results Graph

Interactive HTML graph showing:
- **Pass/Fail status timeline** - Visual test success tracking
- **Test counts** (passed, failed, skipped) - Detailed breakdown per iteration

**Example**: Generated as `test_results_YYYYMMDD_HHMMSS.html`

The graph visualizes:
- Bar charts for pass/fail/skip counts per iteration
- Color-coded status indicators (green=pass, red=fail, yellow=skip)
- Success rate trends over multiple iterations
- Iteration timing and duration

**What to look for in the graph:**
- ✅ **Consistent passes**: Stable test suite
- ❌ **Failed tests**: Investigation needed
- 📉 **Degrading success rate**: Potential environment issues

All graphs are also exported as static images (PNG/SVG/PDF).

### Downloading Result Files

After the test run completes, download commands are displayed:

```bash
============================================================
DOWNLOAD COMMANDS FOR RESULT FILES
============================================================
Copy and paste these commands on your local desktop:
(Replace <your_bastion_host> with your actual bastion hostname)

ssh -t root@<your_bastion_host> "su - zuul -c 'ssh -q controller-0 "cat /path/to/tempest_monitoring_metrics_20251106_120613.csv"'" > tempest_monitoring_metrics_20251106_120613.csv

ssh -t root@<your_bastion_host> "su - zuul -c 'ssh -q controller-0 "cat /path/to/pod_metrics_20251106_114457.html"'" > pod_metrics_20251106_114457.html
```

Simply copy and execute these commands on your local machine to download all result files including interactive HTML graphs.

## Architecture

### Components

```
main.py              # Main orchestrator
├── pod_monitor.py   # Pod metrics collection
├── cr_handler.py    # CR lifecycle management
└── csv_exporter.py  # Data export and visualization
```

### Workflow

1. **Initialization**: Load configuration, setup logging, initialize components
2. **Monitoring Start**: Begin collecting pod metrics in background thread
3. **Test Loop**: 
   - Apply CRs in parallel
   - Wait for completion
   - Verify results
   - Log and export data
   - Repeat until time limit
4. **Shutdown**: 
   - Stop monitoring
   - Generate graphs
   - Display summary

## Troubleshooting

### Common Issues

#### "oc command not found"

Install OpenShift CLI:
```bash
# Download from https://mirror.openshift.com/pub/openshift-v4/clients/ocp/
# Or use your package manager
sudo dnf install openshift-clients  # Fedora/RHEL
```

#### "Failed to get pods: Forbidden"

Ensure you have proper RBAC permissions:
```bash
oc auth can-i get pods -n openstack
oc auth can-i create tempest -n openstack
```

#### "No metrics available"

The `oc adm top` command requires metrics-server to be running:
```bash
oc get deployment metrics-server -n openshift-monitoring
```

#### CR not completing

Check CR timeout in config and verify CR status:
```bash
oc get tempest -n openstack
oc describe tempest <cr-name> -n openstack
```

### Debug Mode

Enable debug logging in `config.yaml`:
```yaml
logging:
  level: "DEBUG"
```

## Advanced Usage

### Custom Pod Patterns

Monitor multiple pod types:
```yaml
monitoring:
  pod_patterns:
    - "designate-*"
    - "neutron-*"
    - "nova-*"
```

### Long-Running Tests

For tests running longer than the default timeout:
```yaml
openshift:
  cr_timeout: 7200  # 2 hours
```

### High-Frequency Monitoring

For more granular metrics:
```yaml
monitoring:
  interval_seconds: 10  # Collect every 10 seconds
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is provided as-is for use with OpenStack deployments.

## Authors

Created for OSP18 Tempest testing and pod monitoring.

## Acknowledgments

- OpenStack Tempest Project
- OpenShift/Kubernetes Community
- Designate Team

