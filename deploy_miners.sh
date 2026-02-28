#!/bin/bash
# Deploy RustChain Mac Miner v2.5.0 to fleet
# Usage: ./deploy_miners.sh [m2|g5|g4|all]

MINER_SRC="/home/scott/bottube-providers/rustchain_mac_miner_v2.5.py"
FP_SRC="/tmp/fingerprint_checks.py"
PW="Elyanlabs12@"
SSH_LEGACY="-o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa"

deploy_m2() {
    echo "=== Deploying to Mac M2 (192.168.0.134) ==="
    local HOST="sophia@192.168.0.134"
    local SSH="sshpass -p $PW ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
    local SCP="sshpass -p $PW scp -o StrictHostKeyChecking=no"

    # Check reachable
    ping -c 1 -W 2 192.168.0.134 >/dev/null 2>&1 || { echo "  M2 is DOWN"; return 1; }

    # Deploy files
    $SCP "$MINER_SRC" "$FP_SRC" $HOST:~/
    echo "  Files deployed"

    # Kill old miner, disable sleep, start new
    $SSH $HOST bash -c "'
        pkill -f rustchain 2>/dev/null
        sleep 2
        # Disable sleep
        sudo pmset -a sleep 0 2>/dev/null
        sudo pmset -a disablesleep 1 2>/dev/null
        # Start new miner
        nohup python3 ~/rustchain_mac_miner_v2.5.py \
            --miner-id macmini-m2-134 \
            --wallet macmini-m2-134 \
            > ~/miner.log 2>&1 &
        sleep 3
        ps aux | grep rustchain | grep -v grep | head -1
        head -15 ~/miner.log
    '"
    echo "  M2 deployment complete"
}

deploy_g5() {
    echo "=== Deploying to G5 (192.168.0.179) ==="
    local HOST="selenamac@192.168.0.179"
    local SSH="sshpass -p $PW ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 $SSH_LEGACY"
    local SCP="sshpass -p $PW scp -o StrictHostKeyChecking=no $SSH_LEGACY"

    ping -c 1 -W 2 192.168.0.179 >/dev/null 2>&1 || { echo "  G5 is DOWN"; return 1; }

    $SCP "$MINER_SRC" "$FP_SRC" $HOST:~/
    echo "  Files deployed"

    $SSH $HOST bash -c "'
        # Stop old shell miner
        launchctl unload ~/Library/LaunchAgents/com.rustchain.miner.plist 2>/dev/null
        pkill -f miner 2>/dev/null
        sleep 2
        # Start Python miner
        nohup python3 ~/rustchain_mac_miner_v2.5.py \
            --wallet g5-selena-179 \
            --miner-id g5-selena-179 \
            > ~/miner_python.log 2>&1 &
        sleep 3
        ps aux | grep rustchain | grep -v grep | head -1
        head -15 ~/miner_python.log
    '"
    echo "  G5 deployment complete"
}

deploy_g4() {
    echo "=== Deploying to Dual G4 (192.168.0.125) ==="
    local HOST="sophia@192.168.0.125"
    local SSH="sshpass -p $PW ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 $SSH_LEGACY"
    local SCP="sshpass -p $PW scp -o StrictHostKeyChecking=no $SSH_LEGACY"

    ping -c 1 -W 2 192.168.0.125 >/dev/null 2>&1 || { echo "  G4 is DOWN"; return 1; }

    $SCP "$MINER_SRC" "$FP_SRC" $HOST:~/rustchain/
    echo "  Files deployed"

    # G4 uses proxy (Tiger can't do modern TLS)
    $SSH $HOST bash -c "'
        pkill -f rustchain_mac 2>/dev/null
        sleep 2
        cd ~/rustchain
        nohup python3 rustchain_mac_miner_v2.5.py \
            --wallet dual-g4-125 \
            --miner-id dual-g4-125 \
            > ~/rustchain/miner_v25.log 2>&1 &
        sleep 3
        ps aux | grep rustchain | grep -v grep | head -1
        head -15 ~/rustchain/miner_v25.log
    '"
    echo "  G4 deployment complete"
}

case "${1:-all}" in
    m2)  deploy_m2 ;;
    g5)  deploy_g5 ;;
    g4)  deploy_g4 ;;
    all)
        deploy_m2
        echo ""
        deploy_g5
        echo ""
        deploy_g4
        ;;
    *)
        echo "Usage: $0 [m2|g5|g4|all]"
        exit 1
        ;;
esac
