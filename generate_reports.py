#!/usr/bin/env python3
"""
Post-Processing Script for Interrupted Test Runs

This script regenerates graphs, web reports, and archives from existing CSV files.
Use this when a test run was interrupted but CSV files were already generated.

Usage:
    python generate_reports.py <results_directory>
    python generate_reports.py results/
    
Example:
    python generate_reports.py /home/zuul/RunTempestMonitorPods/results
"""

import argparse
import logging
import os
import sys
import socket
from pathlib import Path
from csv_exporter import CSVExporter
import pandas as pd
import glob


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def validate_results_directory(results_dir: str) -> bool:
    """
    Validate that the results directory exists and contains CSV files.
    
    Args:
        results_dir: Path to results directory
        
    Returns:
        True if valid, False otherwise
    """
    if not os.path.exists(results_dir):
        return False
    
    if not os.path.isdir(results_dir):
        return False
    
    # Check for at least one CSV file
    csv_files = glob.glob(os.path.join(results_dir, "*.csv"))
    return len(csv_files) > 0


def calculate_test_summary(results_dir: str) -> dict:
    """
    Calculate test summary statistics from results CSV file.
    
    Args:
        results_dir: Path to results directory
        
    Returns:
        Dictionary with test statistics
    """
    # Find results CSV file
    results_csv_pattern = os.path.join(results_dir, "tempest_monitoring_results_*.csv")
    results_files = glob.glob(results_csv_pattern)
    
    if not results_files:
        return {
            'total_runs': 0,
            'total_tests': 0,
            'tests_passed': 0,
            'tests_failed': 0,
            'tests_skipped': 0
        }
    
    # Read the most recent results file
    results_file = sorted(results_files)[-1]
    
    try:
        df = pd.read_csv(results_file)
        
        # Calculate test-level statistics
        total_tests_passed = df['tests_passed'].sum() if 'tests_passed' in df.columns else 0
        total_tests_failed = df['tests_failed'].sum() if 'tests_failed' in df.columns else 0
        total_tests_skipped = df['tests_skipped'].sum() if 'tests_skipped' in df.columns else 0
        total_tests = total_tests_passed + total_tests_failed + total_tests_skipped
        
        return {
            'total_runs': len(df),
            'total_tests': total_tests,
            'tests_passed': total_tests_passed,
            'tests_failed': total_tests_failed,
            'tests_skipped': total_tests_skipped
        }
    except Exception as e:
        logging.warning(f"Could not parse results CSV: {e}")
        return {
            'total_runs': 0,
            'total_tests': 0,
            'tests_passed': 0,
            'tests_failed': 0,
            'tests_skipped': 0
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate reports and archives from existing CSV files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_reports.py results/
  python generate_reports.py /home/zuul/RunTempestMonitorPods/results
  python generate_reports.py results/ --graph-format png
  python generate_reports.py results/ --no-graphs
        """
    )
    parser.add_argument(
        'results_dir',
        help='Path to results directory containing CSV files'
    )
    parser.add_argument(
        '--graph-format',
        choices=['png', 'svg', 'pdf'],
        default='png',
        help='Format for static graph images (default: png)'
    )
    parser.add_argument(
        '--no-graphs',
        action='store_true',
        help='Skip graph generation (only create web report and archive)'
    )
    
    args = parser.parse_args()
    
    logger = setup_logging()
    
    # Validate results directory
    results_dir = os.path.abspath(args.results_dir)
    logger.info(f"Processing results from: {results_dir}")
    
    if not validate_results_directory(results_dir):
        logger.error(f"Invalid results directory: {results_dir}")
        logger.error("Directory must exist and contain CSV files")
        sys.exit(1)
    
    # List CSV files found
    csv_files = glob.glob(os.path.join(results_dir, "*.csv"))
    logger.info(f"Found {len(csv_files)} CSV file(s):")
    for csv_file in sorted(csv_files):
        logger.info(f"  - {os.path.basename(csv_file)}")
    
    # Initialize CSV exporter (point to existing directory, skip archiving!)
    logger.info("\nInitializing CSV exporter...")
    csv_exporter = CSVExporter(
        results_dir=results_dir,
        csv_filename="tempest_monitoring",  # Base filename
        enable_graphs=not args.no_graphs,
        graph_format=args.graph_format,
        skip_archiving=True  # DON'T archive existing CSV files - we need them!
    )
    
    # CRITICAL: Override the CSV file paths with actual existing files
    # (CSVExporter.__init__ creates paths with NEW timestamp, but we need OLD files)
    logger.info("\nMapping existing CSV files to CSVExporter...")
    api_csv_file = None
    error_csv_file = None
    for csv_file in csv_files:
        basename = os.path.basename(csv_file)
        if basename.startswith("old_"):
            continue  # Skip archived files
        
        if "metrics" in basename and "api_requests" not in basename:
            csv_exporter.metrics_csv = csv_file
            logger.info(f"  ✓ Metrics CSV: {basename}")
        elif "results" in basename and "failed" not in basename and "execution" not in basename and "api_requests" not in basename:
            csv_exporter.results_csv = csv_file
            logger.info(f"  ✓ Results CSV: {basename}")
        elif "failed_tests" in basename:
            csv_exporter.failed_tests_csv = csv_file
            logger.info(f"  ✓ Failed Tests CSV: {basename}")
        elif "test_execution_times" in basename:
            csv_exporter.test_execution_csv = csv_file
            logger.info(f"  ✓ Test Execution Times CSV: {basename}")
        elif "api_requests" in basename:
            api_csv_file = csv_file
            logger.info(f"  ✓ API Requests CSV: {basename}")
        elif "error_log" in basename:
            error_csv_file = csv_file
            logger.info(f"  ✓ Error Log CSV: {basename}")
    
    # Generate graphs
    graph_files = []
    
    # Note: Error report HTML cannot be regenerated from CSV alone
    # (it requires the full error text blocks which are too large for CSV parsing)
    # The error_log CSV will still be included in the web report if it exists
    if not args.no_graphs:
        logger.info("\nGenerating graphs from CSV data...")
        try:
            graph_files = csv_exporter.generate_graphs()
            if graph_files:
                logger.info(f"Successfully generated {len(graph_files)} graph(s):")
                for graph_file in graph_files:
                    logger.info(f"  ✓ {os.path.basename(graph_file)}")
            else:
                logger.warning("No graphs were generated (possibly insufficient data)")
        except Exception as e:
            logger.error(f"Error generating graphs: {e}")
            logger.warning("Continuing without graphs...")
        
        # Generate API performance graph if API CSV exists
        if api_csv_file and os.path.exists(api_csv_file):
            logger.info("\nGenerating API performance graph from CSV...")
            try:
                import pandas as pd
                # Read API requests CSV
                api_df = pd.read_csv(api_csv_file)
                if not api_df.empty:
                    # Convert to format expected by generate_api_performance_graph
                    api_data = {
                        'requests': api_df.to_dict('records'),
                        'total_requests': len(api_df),
                        'error_requests': len(api_df[api_df['is_error'] == True]) if 'is_error' in api_df.columns else 0,
                        'by_service': {}
                    }
                    # Group by service
                    if 'service' in api_df.columns:
                        for service, group in api_df.groupby('service'):
                            api_data['by_service'][service] = group.to_dict('records')
                    
                    api_graph = csv_exporter.generate_api_performance_graph(api_data)
                    if api_graph:
                        graph_files.append(api_graph)
                        logger.info(f"  ✓ API graph: {os.path.basename(api_graph)}")
                else:
                    logger.warning("  API CSV is empty, skipping API graph")
            except Exception as e:
                logger.error(f"Error generating API graph: {e}")
                logger.warning("Continuing without API graph...")
    else:
        logger.info("\nSkipping graph generation (--no-graphs specified)")
    
    # Calculate test summary for web report
    logger.info("\nCalculating test summary...")
    test_summary = calculate_test_summary(results_dir)
    logger.info(f"  Total test runs: {test_summary['total_runs']}")
    logger.info(f"  Total tests: {test_summary['total_tests']}")
    logger.info(f"  Tests passed: {test_summary['tests_passed']}")
    logger.info(f"  Tests failed: {test_summary['tests_failed']}")
    logger.info(f"  Tests skipped: {test_summary['tests_skipped']}")
    
    # Generate web report
    logger.info("\nGenerating web report...")
    try:
        web_report_dir = csv_exporter.generate_web_report(test_summary, graph_files)
        if web_report_dir:
            logger.info(f"  ✓ Web report generated: {web_report_dir}")
        else:
            logger.error("  ✗ Failed to generate web report")
    except Exception as e:
        logger.error(f"Error generating web report: {e}")
        web_report_dir = None
    
    # Create archive
    logger.info("\nCreating results archive...")
    try:
        archive_file = csv_exporter.create_results_archive()
        if archive_file and os.path.exists(archive_file):
            logger.info(f"  ✓ Archive created: {os.path.basename(archive_file)}")
            archive_size_mb = os.path.getsize(archive_file) / (1024 * 1024)
            logger.info(f"  Archive size: {archive_size_mb:.2f} MB")
        else:
            logger.error("  ✗ Failed to create archive")
            archive_file = None
    except Exception as e:
        logger.error(f"Error creating archive: {e}")
        archive_file = None
    
    # Print summary
    print("\n" + "="*60)
    print("REPORT GENERATION COMPLETE")
    print("="*60)
    
    print(f"\nResults directory: {results_dir}")
    
    if web_report_dir:
        print(f"\n📊 Web Report: {web_report_dir}/index.html")
        print(f"    Upload the 'web_report' directory to your HTTP server")
    
    # Print download command
    if archive_file and os.path.exists(archive_file):
        # ANSI color codes
        GREEN = "\033[1;32m"
        CYAN = "\033[1;36m"
        YELLOW = "\033[1;33m"
        BLUE = "\033[1;34m"
        RESET = "\033[0m"
        
        print(f"\n{CYAN}{'='*60}{RESET}")
        print(f"{GREEN}DOWNLOAD COMMAND FOR RESULTS ARCHIVE{RESET}")
        print(f"{CYAN}{'='*60}{RESET}")
        print(f"{YELLOW}All results are packaged in a single ZIP file.{RESET}")
        print(f"Copy and paste this command on your local desktop:")
        print(f"(Replace <your_bastion_host> with your actual bastion hostname)\n")
        
        # Get hostname
        try:
            hostname = socket.gethostname()
        except:
            hostname = "controller-0"
        
        archive_path = os.path.abspath(archive_file)
        
        print(f"{BLUE}ssh <your_bastion_host> \"su - zuul -c 'ssh -q {hostname} \\\"base64 {archive_path}\\\"'\" | base64 -d > {os.path.basename(archive_file)}{RESET}\n")
        
        print(f"{YELLOW}Why this command?{RESET}")
        print(f"  • Uses base64 encoding for reliable binary transfer")
        print(f"  • Works through nested SSH (bastion → controller)")
        print(f"  • Single command - no intermediate files")
        print(f"  • Archive contains: index.html + src/ (web report)")
        print(f"{CYAN}{'='*60}{RESET}\n")
    
    logger.info("Done! 🎉")


if __name__ == '__main__':
    main()

