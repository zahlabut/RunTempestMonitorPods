# Quick Start Guide

Get up and running with the OpenStack Tempest Test Runner in 5 minutes!

## Prerequisites

- Python 3.8+
- OpenShift CLI (`oc`) installed
- Access to OpenShift cluster with OSP18

## 5-Minute Setup

### Step 1: Install Dependencies

```bash
# Run the setup script
chmod +x setup.sh
./setup.sh

# Or manually:
pip install -r requirements.txt
```

### Step 2: Configure OpenShift Access

```bash
# Login to your OpenShift cluster
oc login https://your-cluster-url:6443

# Switch to your OpenStack namespace
oc project openstack
```

### Step 3: Edit Configuration

Edit `config.yaml`:

```yaml
# Minimal configuration changes:
cr_files:
  - "designate_tempest_plugin_cr.yaml"
  - "designate_neutron_integration_cr.yaml"

time_to_run_hours: 0.5  # Run for 30 minutes

monitoring:
  namespace: "openstack"  # Your OpenStack namespace
  pod_patterns:
    - "designate-*"       # Pods to monitor
```

### Step 4: Verify CR Files

Make sure your CR files (`designate_tempest_plugin_cr.yaml`, `designate_neutron_integration_cr.yaml`) are properly configured:

- Update `namespace` if different
- Update `openStackConfigMap` and `openStackConfigSecret` names
- Update `containerImage` if using a different image
- Customize `includeList` with your desired tests

### Step 5: Run!

```bash
python main.py
```

## What Happens Next?

1. **Monitoring Starts**: Pod metrics collection begins immediately
2. **Tests Launch**: All CR files are applied in parallel
3. **Data Collection**: Every 30 seconds, pod metrics are collected
4. **Results Logged**: Test results are verified and logged
5. **Loop Continues**: Tests repeat until time limit is reached
6. **Graphs Generated**: Interactive and static graphs are created
7. **Summary Displayed**: Final results summary is shown

## Viewing Results

Check the `results/` directory:

```bash
ls -lh results/

# View metrics CSV
less results/tempest_monitoring_metrics_*.csv

# View test results CSV
less results/tempest_monitoring_results_*.csv

# Open graphs in browser
firefox results/pod_metrics_*.html
firefox results/test_results_*.html
```

## Quick Troubleshooting

### Can't connect to cluster?

```bash
oc whoami  # Verify you're logged in
oc get pods -n openstack  # Verify access to namespace
```

### No metrics appearing?

```bash
# Check if metrics-server is running
oc get pods -n openshift-monitoring | grep metrics

# Try manual metrics collection
oc adm top pods -n openstack
```

### CR not starting?

```bash
# Check CR status
oc get tempest -n openstack

# View CR details
oc describe tempest <cr-name> -n openstack

# Check CR controller logs
oc logs -n openstack-operators <tempest-operator-pod>
```

## Example Output

```
2025-01-05 14:30:22 - INFO - OpenStack Tempest Test Runner Started
2025-01-05 14:30:22 - INFO - Will run tests until: 2025-01-05 15:00:22
2025-01-05 14:30:22 - INFO - Started pod monitoring loop

============================================================
Starting iteration 1
============================================================

2025-01-05 14:30:23 - INFO - [Iteration 1] Started CR: designate-tempest-test-1
2025-01-05 14:30:23 - INFO - [Iteration 1] Started CR: designate-tempest-test-2
2025-01-05 14:30:53 - DEBUG - Collected metrics for 3 pods
2025-01-05 14:35:45 - INFO - [Iteration 1] CR designate-tempest-test-1 completed successfully
2025-01-05 14:35:45 - INFO - [Iteration 1] designate_tempest_plugin_cr.yaml: PASSED
...
```

## Next Steps

- **Customize Tests**: Edit CR files to run different Tempest tests
- **Adjust Duration**: Change `time_to_run_hours` for longer/shorter runs
- **Monitor More Pods**: Add more patterns to `pod_patterns`
- **Analyze Data**: Import CSV files into your favorite data analysis tool
- **Share Graphs**: Upload generated HTML graphs to your team

## Need Help?

Check the full [README.md](README.md) for detailed documentation.

## Pro Tips

1. **Test First**: Run with `time_to_run_hours: 0.1` (6 minutes) to verify setup
2. **Watch Logs**: Use `tail -f tempest_runner.log` to monitor progress
3. **Background Run**: Use `nohup python main.py &` for long runs
4. **Ctrl+C**: Gracefully stops the runner (waits for current tests)
5. **Debug Mode**: Set `logging.level: "DEBUG"` for detailed logs

Happy Testing! 🚀

