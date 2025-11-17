#!/bin/bash
################################################################################
# Error Report Diagnostic Script
#
# This script checks why error reports are not being generated after running
# the Tempest test runner.
#
# Usage:
#   bash check_error_report.sh
#   bash check_error_report.sh /path/to/results/directory
################################################################################

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Results directory (default to ./results)
RESULTS_DIR="${1:-results}"

echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       ERROR REPORT DIAGNOSTIC TOOL                         ║${NC}"
echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo ""

################################################################################
# 1. Check Results Directory
################################################################################
echo -e "${BLUE}[1/6] Checking results directory...${NC}"
echo "Results directory: $RESULTS_DIR"

if [ ! -d "$RESULTS_DIR" ]; then
    echo -e "${RED}✗ Results directory does not exist!${NC}"
    echo "  Please run main.py first or specify correct path."
    exit 1
else
    echo -e "${GREEN}✓ Results directory exists${NC}"
fi
echo ""

################################################################################
# 2. Check for Error Files
################################################################################
echo -e "${BLUE}[2/6] Checking for error report files...${NC}"

ERROR_CSV=$(ls -t $RESULTS_DIR/error_log_*.csv 2>/dev/null | head -1)
ERROR_HTML=$(ls -t $RESULTS_DIR/error_report_*.html 2>/dev/null | head -1)

if [ -n "$ERROR_CSV" ]; then
    echo -e "${GREEN}✓ Error CSV found:${NC} $(basename $ERROR_CSV)"
    ERROR_COUNT=$(tail -n +2 "$ERROR_CSV" | wc -l)
    echo "  Total unique errors: $ERROR_COUNT"
else
    echo -e "${YELLOW}✗ No error_log_*.csv found${NC}"
fi

if [ -n "$ERROR_HTML" ]; then
    echo -e "${GREEN}✓ Error HTML report found:${NC} $(basename $ERROR_HTML)"
else
    echo -e "${YELLOW}✗ No error_report_*.html found${NC}"
fi
echo ""

################################################################################
# 3. Check All CSV Files
################################################################################
echo -e "${BLUE}[3/6] Checking all CSV files in results...${NC}"

CSV_FILES=$(ls -t $RESULTS_DIR/*.csv 2>/dev/null)
if [ -n "$CSV_FILES" ]; then
    echo -e "${GREEN}✓ Found CSV files:${NC}"
    ls -lh $RESULTS_DIR/*.csv | awk '{print "  " $9 " (" $5 ")"}'
else
    echo -e "${RED}✗ No CSV files found!${NC}"
    echo "  Did main.py complete successfully?"
fi
echo ""

################################################################################
# 4. Check OpenStack Pods for ERROR/CRITICAL Logs
################################################################################
echo -e "${BLUE}[4/6] Checking OpenStack pods for ERROR/CRITICAL logs...${NC}"

# Check if oc command is available
if ! command -v oc &> /dev/null; then
    echo -e "${RED}✗ 'oc' command not found${NC}"
    echo "  Cannot check pod logs without OpenShift CLI"
else
    # Get namespace from config or use default
    NAMESPACE="openstack"
    if [ -f "config.yaml" ]; then
        CONFIG_NS=$(grep -A5 "^monitoring:" config.yaml | grep "namespace:" | awk '{print $2}' | tr -d '"')
        [ -n "$CONFIG_NS" ] && NAMESPACE="$CONFIG_NS"
    fi
    
    echo "Namespace: $NAMESPACE"
    
    # Check designate-api pods (example - adjust based on your service)
    API_PODS=$(oc get pods -n $NAMESPACE -o name 2>/dev/null | grep -E "(designate-api|octavia-api|neutron-api|nova-api)" | head -5)
    
    if [ -z "$API_PODS" ]; then
        echo -e "${YELLOW}✗ No API pods found (checked: designate-api, octavia-api, neutron-api, nova-api)${NC}"
    else
        echo -e "${GREEN}✓ Checking recent logs in API pods...${NC}"
        
        TOTAL_ERRORS=0
        for pod in $API_PODS; do
            POD_NAME=$(basename $pod)
            echo ""
            echo "  Checking: $POD_NAME"
            
            # Use the same regex pattern as error_collector.py
            # Pattern: timestamp + PID + ERROR/CRITICAL + module
            ERROR_LINES=$(oc logs $POD_NAME -n $NAMESPACE --tail=500 2>/dev/null | \
                grep -E '^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\.\d+\s+\d+\s+(ERROR|CRITICAL)\s' | \
                wc -l)
            
            if [ $ERROR_LINES -gt 0 ]; then
                echo -e "    ${RED}Found $ERROR_LINES ERROR/CRITICAL log lines${NC}"
                TOTAL_ERRORS=$((TOTAL_ERRORS + ERROR_LINES))
                
                # Show first 3 examples
                echo "    Examples:"
                oc logs $POD_NAME -n $NAMESPACE --tail=500 2>/dev/null | \
                    grep -E '^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\.\d+\s+\d+\s+(ERROR|CRITICAL)\s' | \
                    head -3 | \
                    sed 's/^/      /'
            else
                echo -e "    ${GREEN}✓ No ERROR/CRITICAL logs found${NC}"
            fi
        done
        
        echo ""
        if [ $TOTAL_ERRORS -gt 0 ]; then
            echo -e "${YELLOW}⚠ Total ERROR/CRITICAL lines found: $TOTAL_ERRORS${NC}"
            echo "  These should be captured in error report if main.py completed."
        else
            echo -e "${GREEN}✓ No ERROR/CRITICAL logs found in any API pod${NC}"
            echo "  This explains why no error report was generated!"
        fi
    fi
fi
echo ""

################################################################################
# 5. Check for Log Output from main.py
################################################################################
echo -e "${BLUE}[5/6] Checking for main.py execution logs...${NC}"

# Check common log locations
LOG_FILES=(
    "tempest_runner.log"
    "output.log"
    "nohup.out"
)

FOUND_LOG=false
for log_file in "${LOG_FILES[@]}"; do
    if [ -f "$log_file" ]; then
        echo -e "${GREEN}✓ Found log file:${NC} $log_file"
        FOUND_LOG=true
        
        # Check for error collection phase
        if grep -q "Collecting ERROR/CRITICAL logs" "$log_file" 2>/dev/null; then
            echo ""
            echo "  Error collection phase output:"
            echo "  ----------------------------------------"
            grep -A 15 "Collecting ERROR/CRITICAL logs" "$log_file" | tail -20 | sed 's/^/  /'
            echo "  ----------------------------------------"
        else
            echo -e "  ${YELLOW}⚠ Error collection phase not found in log${NC}"
            echo "    (execution may have been interrupted before this phase)"
        fi
        break
    fi
done

if [ "$FOUND_LOG" = false ]; then
    echo -e "${YELLOW}✗ No log files found${NC}"
    echo "  Checked: ${LOG_FILES[*]}"
    echo "  If you ran in foreground, check terminal scrollback."
fi
echo ""

################################################################################
# 6. Check Web Report
################################################################################
echo -e "${BLUE}[6/6] Checking web report...${NC}"

WEB_REPORT_DIR="$RESULTS_DIR/web_report"
INDEX_HTML="$WEB_REPORT_DIR/index.html"

if [ -f "$INDEX_HTML" ]; then
    echo -e "${GREEN}✓ Web report exists:${NC} $INDEX_HTML"
    
    # Check if error report is linked in index.html
    if grep -q "error_report_" "$INDEX_HTML"; then
        echo -e "${GREEN}✓ Error report is linked in index.html${NC}"
    else
        echo -e "${YELLOW}✗ Error report NOT linked in index.html${NC}"
        echo "  This is expected if no errors were found."
    fi
    
    # Check what graphs are linked
    echo ""
    echo "  Graphs in web report:"
    grep -o 'href="src/[^"]*\.html"' "$INDEX_HTML" | sed 's/href="src\//  - /' | sed 's/"//' | sort -u
    
else
    echo -e "${YELLOW}✗ Web report not found${NC}"
    echo "  Expected location: $INDEX_HTML"
fi
echo ""

################################################################################
# Summary and Recommendations
################################################################################
echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       SUMMARY & RECOMMENDATIONS                            ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ -n "$ERROR_CSV" ] && [ -n "$ERROR_HTML" ]; then
    echo -e "${GREEN}✓ Error report files exist!${NC}"
    echo "  - CSV: $(basename $ERROR_CSV)"
    echo "  - HTML: $(basename $ERROR_HTML)"
    echo ""
    echo "If not in web report, try regenerating:"
    echo "  python generate_reports.py $RESULTS_DIR"
    
elif [ $TOTAL_ERRORS -gt 0 ] 2>/dev/null; then
    echo -e "${YELLOW}⚠ ERROR logs exist in pods, but no error report was generated.${NC}"
    echo ""
    echo "Possible causes:"
    echo "  1. Execution was interrupted before error collection completed"
    echo "  2. Error collection phase encountered an exception"
    echo "  3. Logs are outside the time window analyzed (last iteration only)"
    echo ""
    echo "Solutions:"
    echo "  1. Run main.py again and let it complete fully"
    echo "  2. Check for exceptions in logs around 'Collecting ERROR/CRITICAL'"
    echo "  3. Verify time_to_run_hours allows at least one iteration to complete"
    
else
    echo -e "${GREEN}✓ No ERROR/CRITICAL logs found in OpenStack pods!${NC}"
    echo ""
    echo "This is GOOD NEWS - your OpenStack services are running cleanly!"
    echo ""
    echo "Recent fix (V1.3): Error collector now only captures actual ERROR/CRITICAL"
    echo "log levels, not 'ERROR' appearing in message content (e.g., 'status ERROR')."
    echo ""
    echo "No error report is generated when there are no errors to report."
fi

echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"

