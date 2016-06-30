#!/bin/bash

# Copyright 2015, Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This script is just intended to facilitate manual testing

set -e

# A POSIX variable
OPTIND=1 # Reset in case getopts has been used previously in the shell.

SERVER="OS::Nova::Server"
IMAGE="OS::Glance::Image"
VOLUME="OS::Cinder::Volume"
ZONE="OS::Designate::Zone"
RECORDSET="OS::Designate::RecordSet"

base_name="demo"
types="$SERVER $IMAGE $VOLUME $METADEF $ZONE $RECORDSET"
number=1
devstack_home="$HOME"/devstack
server_flavor="m1.tinier"
server_image="cirros-0.3.4-x86_64-disk"
image_file=$( cd "$(dirname "$0")" ; pwd -P )"/"$(basename "$0")
network=public

#TODO Add Neutron resources.

function print_help {
    echo
    echo "Usage:"
    echo ""
    echo " You must pre-set all your OS_* environment variables. For example:"
    echo "  $source <devstack_home>/openrc admin demo"
    echo "  -n the base name to use for all resources. default: $base_name"
    echo "  -t the resource types to generate. default: $types"
    echo "  -x the number of each type of resource to create. default: $number"
    echo
}

while getopts "h?:d:n:u:p:t:x:" opt; do
    case "$opt" in
    h|\?)
        print_help;
        exit 2
        ;;
    n)  base_name=$OPTARG
        ;;
    t)  types=$OPTARG
        ;;
    x)  number=$OPTARG
        ;;
    esac
done

shift $((OPTIND-1))

[ "$1" = "--" ] && shift

function echo_opts {
  echo
  echo "base_name=$base_name, types='$types', number='$number'"
  echo
}

echo_opts

# End of file

function info {
    echo
    echo "$1"
    echo
}

sample_properties[0]="--property tag=python,fedora --property sw_runtime_python_version=2.7"
sample_tags[0]="--tag python --tag fedora"
sample_properties[1]="--property tag=python,fedora,dev --property sw_runtime_python_version=3.4"
sample_tags[1]="--tag python --tag fedora --tag dev"
sample_properties[2]="--property tag=python,debian,dev --property sw_runtime_python_version=3.4"
sample_tags[2]="--tag python --tag debian --tag dev"
sample_properties[3]="--property tag=apache,python,fedora,prod,web --property sw_webserver_apache_version=2.2.31"
sample_tags[3]="--tag apache --tag debian --python --tag prod --tag web"
sample_properties[4]="--property tag=apache,web,fedora --property sw_webserver_apache_version=2.4.18"
sample_tags[4]="--tag apache --tag fedora --tag web"
sample_properties[5]="--property tag=python,apache,web,debian --property sw_runtime_python_version=3.4 --property sw_webserver_apache_version=2.4.18"
sample_tags[5]="--tag python --tag apache --tag web"
sample_properties[6]="--property tag=python,apache,web,debian --property sw_webserver_apache_version=2.2.31"
sample_tags[6]="--tag python --tag apache --tag web"
sample_metadata_idx=-1

function incr_metadata_samples () {
    sample_metadata_idx=$((sample_metadata_idx+1))
    if [ $sample_metadata_idx -eq 7 ]
    then
      sample_metadata_idx=0
    fi

    export properties=${sample_properties[$sample_metadata_idx]}
    export tags=${sample_tags[$sample_metadata_idx]}
}

function initialize_flavor {
    if [[ "$types" != *"$SERVER"*  ]]
    then
      echo "Skipping flavor initialization"
      return 0
    fi

    (set -x; openstack flavor create --ram 64 --disk 1 --ephemeral 0 --public --vcpus 1 "$server_flavor" || true)
}

function create_server () {
    if [[ "$types" != *"$SERVER"*  ]]
    then
          echo "Skipping servers"
      return 0
    fi
    info "$SERVER"
    export server_name="$base_name"
    # TODO Configurable network id
    export net_id=$(openstack network show $network -c id -f value)
    (set -x; openstack server create --image "$server_image" --flavor "$server_flavor" --nic net-id=$net_id $properties "$server_name")

    while : ; do
      server_status=$(openstack server show "$server_name" --column status -f value)
      echo "Server status $server_status"
      if [ "$server_status" ==  "ACTIVE" ]; then
          break
      fi
      sleep 1
    done

    nova stop "$server_name"
}

function create_image () {
    if [[ "$types" != *"$IMAGE"* ]]
    then
      echo "Skipping images"
      return 0
    fi
    info "$IMAGE"
    export image_name="$base_name"
    (set -x; openstack image create --container-format bare --disk-format raw --file "$image_file" $tags "$image_name")
}

function create_volume () {
    if [[ "$types" != *"$VOLUME"* ]]
    then
      echo "Skipping volumes and volume snapshots"
      return 0
    fi
    info "$VOLUME"
    export volume_name="$base_name"
    (set -x; openstack volume create --size 1 $properties "$volume_name")

    # TODO volume snapshots -openstack client doesn't seem to support yet
}

function create_designate_resources {
    if [[ "$types" != *"OS::Designate"* ]]
    then
          echo "Skipping designate:"
      return 0
    fi
    info "OS::Designate::*"
    export zone_name="$base_name"."$base_name".
    (set -x; openstack zone create "$zone_name" --email travis@dnstest.net)

    while : ; do
      zone_status=$(openstack zone show "$zone_name" --column status -f value)
      echo "Zone status $zone_status"
      if [ "$zone_status" ==  "ACTIVE" ]; then
          break
      fi
      sleep 1
    done

    export zone_id=$(openstack zone show "$zone_name" --column id -f value)
    (set -x; designate record-create "$zone_id" --name www."$zone_name" --type A --data 192.0.2.1)
}

counter=1
orig_base_name="$base_name"
initialize_flavor
while [  "$counter" -le "$number" ]; do
  if [ "$number" -gt 1 ]
  then
    base_name="$orig_base_name"_"$counter"
    echo "Executing run $counter. Using Base Name: $base_name"
  fi
  incr_metadata_samples
  create_server
  create_image
  create_volume
  create_designate_resources
  let counter=counter+1
done

echo_opts
echo "Complete"
