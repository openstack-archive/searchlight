#!/bin/bash

set -ex

pushd $BASE/new/devstack

export KEEP_LOCALRC=1
export ENABLED_SERVICES=mysql,key,searchlight,searchlight-api

# Pass through any SEARCHLIGHT_ env vars to the localrc file
env | grep -E "^SEARCHLIGHT_" >> $BASE/new/devstack/local.conf || :

popd

# Run DevStack Gate
$BASE/new/devstack-gate/devstack-vm-gate.sh
